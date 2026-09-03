"""
Generate the self-signed certificate MeetScribe's HTTPS listener uses.

Remote browser capture needs a secure context — Chrome refuses getUserMedia and
getDisplayMedia on plain http://<lan-ip>. This mints a long-lived certificate
covering this PC's LAN address so the other laptop can reach it over https.

The certificate is self-signed, so the first visit shows a browser warning.
Click "Advanced -> Proceed"; Chrome then treats the origin as secure and audio
capture works. Run again after your LAN IP changes.

    python make_cert.py
"""

import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = Path(__file__).parent / "certs"


def local_ips():
    """Every IPv4 address worth putting in the certificate."""
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            # Skip WSL/Hyper-V virtual adapters — the laptop cannot route to them.
            if not ip.startswith(("169.254.", "172.")):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


def main():
    CERT_DIR.mkdir(exist_ok=True)
    hostname = socket.gethostname()
    ips = local_ips()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "MeetScribe"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MeetScribe Local"),
    ])

    alt_names = [x509.DNSName("localhost"), x509.DNSName(hostname)]
    alt_names += [x509.IPAddress(ipaddress.IPv4Address(ip)) for ip in ips]

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    (CERT_DIR / "key.pem").write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    (CERT_DIR / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Certificate written to {CERT_DIR}")
    print(f"  hostname: {hostname}")
    for ip in ips:
        print(f"  https://{ip}:5443")


if __name__ == "__main__":
    main()
