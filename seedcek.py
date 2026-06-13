#!/usr/bin/env python3
"""
Bitcoin Seed Checker & Recovery Tool - Strict Realtime Version
Mekanisme: WAJIB online. Akan pause jika koneksi terputus.
"""
import argparse
import time
import sys
import requests
from tqdm import tqdm
from mnemonic import Mnemonic
from embit import bip39, bip32, script
from embit.networks import NETWORKS
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import deque
from datetime import datetime

# ============ KONFIGURASI ============
DERIVATIONS = [
    ("Legacy (BIP44)", "m/44'/0'/0'/0/0", lambda k: script.p2pkh(k.key).address(NETWORKS['main'])),
    ("SegWit (BIP49)", "m/49'/0'/0'/0/0", lambda k: script.p2sh(script.p2wpkh(k.key)).address(NETWORKS['main'])),
    ("Native SegWit (BIP84)", "m/84'/0'/0'/0/0", lambda k: script.p2wpkh(k.key).address(NETWORKS['main']))
]

MEMPOOL_API = {
    'single': 'https://mempool.space/api/address/{}',
    'batch': 'https://mempool.space/api/v1/addresses'
}

PUBLIC_PROXIES = []

file_lock = threading.Lock()
request_history = deque(maxlen=100)

# ============ ADAPTIVE RATE LIMITING ============
class AdaptiveRateLimiter:
    def __init__(self, initial_delay=0.5, min_delay=0.1, max_delay=5.0):
        self.current_delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.success_count = 0
        self.fail_count = 0
        self.lock = threading.Lock()

    def adjust(self, success):
        with self.lock:
            if success:
                self.success_count += 1
                if self.success_count % 10 == 0:
                    self.current_delay = max(self.min_delay, self.current_delay * 0.9)
                self.fail_count = 0
            else:
                self.fail_count += 1
                if self.fail_count % 3 == 0:
                    self.current_delay = min(self.max_delay, self.current_delay * 1.5)
                self.success_count = 0

    def wait(self):
        time.sleep(self.current_delay)
        return self.current_delay

    def get_delay(self):
        return self.current_delay

rate_limiter = AdaptiveRateLimiter(initial_delay=0.5)

# ============ PROXY MANAGEMENT ============
class ProxyManager:
    def __init__(self, proxy_list=None, rotate_on_fail=True):
        self.proxies = proxy_list or PUBLIC_PROXIES.copy()
        self.current_index = 0
        self.rotate_on_fail = rotate_on_fail
        self.lock = threading.Lock()

    def get_proxy(self):
        if not self.proxies:
            return None
        with self.lock:
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            return {'http': proxy, 'https': proxy}

    def mark_failed(self, proxy):
        if self.rotate_on_fail and proxy in self.proxies:
            with self.lock:
                self.proxies.remove(proxy)
                self.proxies.append(proxy)

proxy_manager = ProxyManager()

# ============ STRICT CONNECTION MANAGEMENT ============
def check_internet_connection():
    """Cek koneksi internet ke mempool.space sebelum mulai"""
    print("[*] Mengecek koneksi internet ke mempool.space...")
    try:
        response = requests.get("https://mempool.space/api/blocks/tip/height", timeout=10)
        if response.status_code == 200:
            print("[✓] Koneksi internet stabil. Script siap berjalan secara REALTIME.")
            return True
        else:
            print(f"[!] Gagal terhubung ke mempool.space (Status HTTP: {response.status_code})")
            return False
    except requests.exceptions.RequestException as e:
        print("\n" + "="*70)
        print("[!!!] ERROR KRITIS: TIDAK ADA KONEKSI INTERNET!")
        print("[!!!] Script TIDAK DAPAT BERJALAN dalam mode offline.")
        print("[!!!] Pastikan Anda terhubung ke internet untuk mengecek wallet secara realtime.")
        print(f"[!] Detail Error: {e}")
        print("="*70 + "\n")
        return False

def wait_for_connection():
    """Blokir eksekusi sampai koneksi internet kembali"""
    print("\n" + "="*70)
    print("[!] PERINGATAN: Koneksi internet terputus atau API tidak merespon!")
    print("[!] Script DIJEDA (PAUSE). Menunggu koneksi kembali...")
    print("[!] Tekan Ctrl+C jika Anda ingin membatalkan dan keluar.")
    print("="*70)
    
    while True:
        try:
            response = requests.get("https://mempool.space/api/blocks/tip/height", timeout=5)
            if response.status_code == 200:
                print("\n[✓] Koneksi internet kembali stabil. Melanjutkan pengecekan...\n")
                # Safety delay agar tidak langsung di-ban setelah reconnect
                rate_limiter.current_delay = max(rate_limiter.current_delay, 1.5)
                return True
        except requests.exceptions.RequestException:
            pass
        except KeyboardInterrupt:
            print("\n[!] Dibatalkan oleh pengguna. Script dihentikan.")
            sys.exit(1)
        time.sleep(3)  # Cek setiap 3 detik

# ============ API CALLER DENGAN STRICT FALLBACK ============
def call_mempool_api(addresses, use_batch=True):
    if not addresses:
        return None
    if use_batch and len(addresses) > 1:
        return call_mempool_batch(addresses)
    return call_mempool_single(addresses[0])

def call_mempool_batch(addresses):
    addrs = [addr for _, addr in addresses]
    proxies = proxy_manager.get_proxy()
    
    for attempt in range(3):
        try:
            response = requests.post(
                MEMPOOL_API['batch'],
                json={"addresses": addrs},
                timeout=15,
                proxies=proxies
            )
            if response.status_code == 200:
                data = response.json()
                results = {}
                for addr_data in data.get('addresses', []):
                    balance_sats = addr_data.get('chain_stats', {}).get('funded_txo_sum', 0) - \
                                   addr_data.get('chain_stats', {}).get('spent_txo_sum', 0)
                    results[addr_data['address']] = balance_sats / 1e8
                rate_limiter.adjust(True)
                return results
            elif response.status_code == 429:
                wait_time = 30 * (attempt + 1)
                print(f"\n[!] Rate limit tercapai. Menunggu {wait_time} detik...")
                time.sleep(wait_time)
                rate_limiter.adjust(False)
                continue
            else:
                if proxies:
                    proxy_manager.mark_failed(list(proxies.values())[0])
                    proxies = proxy_manager.get_proxy()
                rate_limiter.adjust(False)
                time.sleep(2)
        except requests.exceptions.RequestException:
            # INI ADALAH TANDA PUTUS KONEKSI / OFFLINE
            wait_for_connection()  # Script akan pause di sini sampai online
            proxies = proxy_manager.get_proxy()
            continue  # Coba lagi setelah koneksi kembali
    return None

def call_mempool_single(address):
    addr = address[1] if isinstance(address, tuple) else address
    proxies = proxy_manager.get_proxy()
    
    for attempt in range(3):
        try:
            response = requests.get(
                MEMPOOL_API['single'].format(addr),
                timeout=10,
                proxies=proxies
            )
            if response.status_code == 200:
                data = response.json()
                balance_sats = data.get('chain_stats', {}).get('funded_txo_sum', 0) - \
                               data.get('chain_stats', {}).get('spent_txo_sum', 0)
                rate_limiter.adjust(True)
                return {addr: balance_sats / 1e8}
            elif response.status_code == 429:
                wait_time = 30 * (attempt + 1)
                print(f"\n[!] Rate limit. Menunggu {wait_time} detik...")
                time.sleep(wait_time)
                rate_limiter.adjust(False)
                continue
            else:
                if proxies:
                    proxy_manager.mark_failed(list(proxies.values())[0])
                    proxies = proxy_manager.get_proxy()
                rate_limiter.adjust(False)
                time.sleep(2)
        except requests.exceptions.RequestException:
            # INI ADALAH TANDA PUTUS KONEKSI / OFFLINE
            wait_for_connection()  # Script akan pause di sini sampai online
            proxies = proxy_manager.get_proxy()
            continue  # Coba lagi setelah koneksi kembali
    return None

def check_balances(addresses):
    return call_mempool_api(addresses, use_batch=len(addresses) > 1)

# ============ CORE FUNCTIONS ============
def get_addresses_from_seed(phrase, passphrase=""):
    if not Mnemonic("english").check(phrase):
        return None
    try:
        seed = bip39.mnemonic_to_seed(phrase, passphrase=passphrase)
        root = bip32.HDKey.from_seed(seed)
        addresses = []
        for label, path, derive_func in DERIVATIONS:
            try:
                derived = root.derive(path)
                addr = derive_func(derived)
                addresses.append((label, addr))
            except Exception:
                continue
        return addresses if addresses else None
    except Exception:
        return None

def save_result(phrase, addresses, balances, output_file):
    with file_lock, open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SEED DITEMUKAN!\n")
        f.write(f"Seed: {phrase}\n")
        total_balance = 0
        for label, addr in addresses:
            balance = balances.get(addr, 0.0)
            total_balance += balance
            f.write(f"  {label}: {addr} | Saldo: {balance:.8f} BTC\n")
        f.write(f"Total Saldo: {total_balance:.8f} BTC\n")
        f.write(f"{'='*50}\n")
    print(f"\n[✓] TERSIMPAN! Total: {total_balance:.8f} BTC")

def check_single_seed(phrase, passphrase, output_file):
    addrs = get_addresses_from_seed(phrase, passphrase)
    if not addrs:
        return None
    
    current_delay = rate_limiter.wait()
    balances = check_balances(addrs)
    
    # Jika balances tetap None setelah retry (sangat jarang karena ada wait_for_connection)
    if balances is None:
        print(f"\n[!] Gagal mendapatkan data untuk seed ini. Melewati...")
        return None
        
    if sum(balances.values()) > 0:
        print(f"\n{'!'*50}")
        print(f"[!!!] WALLET DITEMUKAN!")
        print(f"Seed: {phrase}")
        for label, addr in addrs:
            bal = balances.get(addr, 0)
            if bal > 0:
                print(f"  {label}: {addr} -> {bal:.8f} BTC")
        print(f"{'!'*50}")
        save_result(phrase, addrs, balances, output_file)
        return (phrase, addrs, balances)
    return None

# ============ MODE CHECK FILE ============
def mode_file_check(args):
    with open(args.file, 'r', encoding='utf-8') as f:
        seeds = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"\n{'='*50}")
    print(f"[*] BITCOIN SEED CHECKER v2.0 (STRICT REALTIME MODE)")
    print(f"[*] File: {args.file} ({len(seeds)} seeds)")
    print(f"[*] Threads: {args.threads}")
    print(f"[*] Delay awal: {rate_limiter.get_delay():.2f} detik (adaptive)")
    print(f"[*] Proxy: {'Aktif' if proxy_manager.proxies else 'Tidak'}")
    print(f"[*] API: mempool.space")
    print(f"{'='*50}\n")
    
    found_wallets = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(check_single_seed, seed, args.passphrase, args.output): seed
            for seed in seeds
        }
        with tqdm(total=len(seeds), desc="Memeriksa Seed", unit="seed", ascii=True) as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result:
                    found_wallets.append(result)
                pbar.update(1)
                pbar.set_postfix({
                    'Delay': f"{rate_limiter.get_delay():.2f}s",
                    'Found': len(found_wallets)
                })
                
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"[*] SELESAI!")
    print(f"[*] Total seed diperiksa: {len(seeds)}")
    print(f"[*] Wallet ditemukan: {len(found_wallets)}")
    print(f"[*] Waktu: {elapsed:.1f} detik")
    print(f"[*] Hasil disimpan di: {args.output}")
    print(f"{'='*50}")

# ============ MODE RECOVERY ============
def mode_recover(args):
    if len(args.recover) not in (11, 23):
        print("[!] Error: Butuh 11 kata (untuk seed 12-kata) atau 23 kata (untuk seed 24-kata)")
        print(f"    Anda memasukkan {len(args.recover)} kata.")
        return
        
    mnemo = Mnemonic("english")
    target_len = len(args.recover) + 1
    
    print(f"\n{'='*50}")
    print(f"[*] MODE RECOVERY - Seed {target_len}-kata (STRICT REALTIME)")
    print(f"[*] Mencari kata yang hilang dari 2048 kemungkinan...")
    print(f"{'='*50}\n")
    
    found = False
    start_time = time.time()
    
    for idx, missing_word in enumerate(tqdm(mnemo.wordlist, desc="Mencoba kata", unit="kata", ascii=True)):
        test_phrase = " ".join(args.recover + [missing_word])
        if mnemo.check(test_phrase):
            addrs = get_addresses_from_seed(test_phrase, args.passphrase)
            if addrs:
                rate_limiter.wait()
                balances = check_balances(addrs)
                
                if balances is None:
                    continue  # Akan dihandle oleh wait_for_connection di dalam check_balances                    
                if sum(balances.values()) > 0:
                    print(f"\n{'!'*50}")
                    print(f"[!!!] KATA HILANG DITEMUKAN!")
                    print(f"Kata ke-{target_len}: '{missing_word}'")
                    print(f"Seed lengkap: {test_phrase}")
                    print(f"{'!'*50}")
                    save_result(test_phrase, addrs, balances, args.output)
                    found = True
                    break
                    
        if (idx + 1) % 100 == 0 and not found:
            tqdm.write(f"[*] Sudah mencoba {idx+1}/2048 kata... Delay: {rate_limiter.get_delay():.2f}s")
            
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    if found:
        print(f"[✓] SUKSES! Kata ditemukan dalam {elapsed:.1f} detik")
    else:
        print(f"[✗] Tidak ditemukan wallet dengan saldo")
    print(f"{'='*50}")

# ============ MAIN ============
def setup_args():
    parser = argparse.ArgumentParser(description='Bitcoin Seed Checker (Strict Realtime)')
    parser.add_argument('-f', '--file', help='File berisi daftar seed phrase')
    parser.add_argument('-r', '--recover', nargs='+', help='11/23 kata untuk recovery')
    parser.add_argument('-p', '--passphrase', default='', help='Passphrase BIP39')
    parser.add_argument('-o', '--output', default='hasil_temuan.txt', help='File output')
    parser.add_argument('-t', '--threads', type=int, default=3, help='Jumlah thread (default: 3, lebih aman)')
    parser.add_argument('--proxy', help='File berisi daftar proxy')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay awal')
    parser.add_argument('--min-delay', type=float, default=0.1, help='Delay minimal')
    parser.add_argument('--max-delay', type=float, default=5.0, help='Delay maksimal')
    return parser.parse_args()

def load_proxies_from_file(proxy_file):
    try:
        with open(proxy_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"[!] Gagal load proxy file: {e}")
        return []

def main():
    # 1. WAJIB CEK KONEKSI DI AWAL
    if not check_internet_connection():
        sys.exit(1)  # Berhenti total jika offline
        
    args = setup_args()    
    global rate_limiter
    rate_limiter = AdaptiveRateLimiter(
        initial_delay=args.delay,
        min_delay=args.min_delay,
        max_delay=args.max_delay
    )
    
    if args.proxy:
        proxy_list = load_proxies_from_file(args.proxy)
        if proxy_list:
            global proxy_manager
            proxy_manager = ProxyManager(proxy_list)
            print(f"[*] Memuat {len(proxy_list)} proxy dari {args.proxy}")
            
    if args.file:
        mode_file_check(args)
    elif args.recover:
        mode_recover(args)
    else:
        print("Gunakan salah satu mode:")
        print("  1. Cek dari file: python seedcek.py -f daftar_seed.txt")
        print("  2. Recovery kata hilang: python seedcek.py -r kata1 kata2 ... kata11")

if __name__ == '__main__':
    main()