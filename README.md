# Bitcoin Seed Checker & Recovery Tool (Strict Realtime)

## Deskripsi
Script Python untuk memeriksa saldo Bitcoin pada seed phrase BIP39 (12/24 kata) secara realtime melalui API mempool.space. Mendukung pemulihan kata yang hilang (11 atau 23 kata). **WAJIB online** – script akan pause jika koneksi terputus.

## Fitur
- Cek banyak seed dari file teks
- Recovery kata hilang (11 → 12 kata, 23 → 24 kata)
- 3 jalur derivasi: Legacy (BIP44), SegWit (BIP49), Native SegWit (BIP84)
- Adaptive rate limiting (delay menyesuaikan otomatis)
- Dukungan proxy (rotasi saat gagal)
- Multi-threading (default 3 thread)
- Auto-save hasil temuan ke file

## Instalasi
```bash
git clone https://github.com/username/bitcoin-seed-checker.git
cd bitcoin-seed-checker
pip install -r requirements.txt