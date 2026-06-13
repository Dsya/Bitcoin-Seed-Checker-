# Bitcoin Seed Checker & Recovery Tool (Strict Realtime)

Check Bitcoin BIP39 seed phrases (12/24 words) for balance across legacy, SegWit, and native SegWit addresses. Recover a missing word in a seed phrase (11 or 23 words). All checks are done in realtime via mempool.space API – requires active internet connection.

✨ Features:
- ✅ Check multiple seeds from a file (multi-threaded)
- 🔁 Recover missing word (2048 possibilities)
- 📡 Strict online mode – auto-pauses if connection drops
- ⏱️ Adaptive rate limiting (avoids API bans)
- 🌐 Proxy support (rotate on failure)
- 📝 Saves found wallets with timestamp & balances
- 🐍 Python 3 (mnemonic, embit, requests, tqdm)

⚠️ Warning: This tool is for educational & recovery purposes only. Never share your seed phrases.

🚀 Quick usage:
  python seedcek.py -f seeds.txt
  python seedcek.py -r word1 word2 ... word11
  
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

## markdown
![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Bitcoin](https://img.shields.io/badge/Bitcoin-Validation-orange)

## bash
# Mode file
python seedcek.py -f daftar_seed.txt -o hasil.txt

# Mode recovery (11 kata untuk seed 12-kata)
python seedcek.py -r kata1 kata2 ... kata11

# Dengan proxy
python seedcek.py -f seeds.txt --proxy proxies.txt

# Atur delay awal
python seedcek.py -f seeds.txt --delay 0.3 --min-delay 0.1 --max-delay 3.0