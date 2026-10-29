#!/usr/bin/env python3
"""
Script standalone untuk test autentikasi API Key SafeTrade (Peatio/Barong).

Jalankan dari direktori ini di VPS:
    python3 test_safetrade_auth.py

Script ini TIDAK menyentuh database maupun mengirim notifikasi Telegram.
Hanya melakukan request GET ke endpoint saldo SafeTrade dengan beberapa
variasi skema HMAC signing, supaya kalau skema default gagal kita bisa
langsung tahu skema mana yang berhasil tanpa harus bolak-balik edit kode.

Butuh SAFETRADE_API_KEY dan SAFETRADE_API_SECRET. Cara isi (pilih salah satu):
  1. Taruh di file .env pada direktori yang sama dengan script ini, contoh:
       SAFETRADE_API_KEY=xxxx
       SAFETRADE_API_SECRET=yyyy
  2. Atau export sebagai environment variable sebelum menjalankan script:
       export SAFETRADE_API_KEY=xxxx
       export SAFETRADE_API_SECRET=yyyy
       python3 test_safetrade_auth.py
"""

import os
import sys
import time
import hmac
import hashlib
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # fallback: manual parse .env kalau python-dotenv belum terinstall
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

try:
    import requests
except ImportError:
    print("Modul 'requests' tidak ditemukan. Install dulu: pip install requests")
    print("(atau: pip install requests python-dotenv)")
    sys.exit(1)

API_KEY = os.getenv("SAFETRADE_API_KEY", "").strip()
API_SECRET = os.getenv("SAFETRADE_API_SECRET", "").strip()

BASE_URL = "https://safetrade.com/api/v2/peatio"
BALANCE_ENDPOINTS = [
    "/account/balances",
    "/account/balances/summary",
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_variants():
    """
    Menghasilkan daftar variasi (nama, nonce, signature_payload_builder, header_style)
    untuk dicoba satu per satu. Peatio fork berbeda-beda kadang beda format nonce
    atau urutan payload signature, jadi kita coba beberapa kombinasi umum.
    """
    nonce_ms = str(int(time.time() * 1000))
    nonce_s = str(int(time.time()))

    variants = []

    # Variant 1: standar Peatio - nonce(ms) + apikey, header title-case
    variants.append({
        "name": "nonce(ms) + apikey, header Title-Case",
        "nonce": nonce_ms,
        "payload": nonce_ms + API_KEY,
        "headers_style": "title",
    })

    # Variant 2: nonce dalam detik (bukan ms)
    variants.append({
        "name": "nonce(detik) + apikey, header Title-Case",
        "nonce": nonce_s,
        "payload": nonce_s + API_KEY,
        "headers_style": "title",
    })

    # Variant 3: urutan dibalik -> apikey + nonce
    variants.append({
        "name": "apikey + nonce(ms), header Title-Case",
        "nonce": nonce_ms,
        "payload": API_KEY + nonce_ms,
        "headers_style": "title",
    })

    # Variant 4: header lowercase
    variants.append({
        "name": "nonce(ms) + apikey, header lowercase",
        "nonce": nonce_ms,
        "payload": nonce_ms + API_KEY,
        "headers_style": "lower",
    })

    return variants


def headers_for(style: str, api_key: str, nonce: str, signature: str) -> dict:
    if style == "lower":
        return {
            "x-auth-apikey": api_key,
            "x-auth-nonce": nonce,
            "x-auth-signature": signature,
            "accept": "application/json",
            "user-agent": UA,
        }
    # default: Title-Case (dipakai banyak implementasi Peatio reference)
    return {
        "X-Auth-Apikey": api_key,
        "X-Auth-Nonce": nonce,
        "X-Auth-Signature": signature,
        "Accept": "application/json",
        "User-Agent": UA,
    }


def main():
    print("=" * 70)
    print("TEST AUTENTIKASI SAFETRADE API KEY")
    print("=" * 70)

    if not API_KEY or not API_SECRET:
        print("ERROR: SAFETRADE_API_KEY / SAFETRADE_API_SECRET kosong.")
        print("Isi lewat file .env di direktori ini, atau export sebagai env var.")
        sys.exit(1)

    print(f"API Key   : {API_KEY[:4]}...{API_KEY[-4:]} (len={len(API_KEY)})")
    print(f"API Secret: {'*' * 8} (len={len(API_SECRET)})")
    print()

    # 0. Sanity check dulu: pastikan domain bisa diakses sama sekali dari
    # jaringan ini (endpoint publik, tanpa auth). Kalau ini pun gagal,
    # masalahnya jaringan/IP-block, bukan auth.
    print("-- Sanity check endpoint publik (tanpa auth) --")
    try:
        res = requests.get(
            f"{BASE_URL}/public/markets/tickers",
            headers={"Accept": "application/json", "User-Agent": UA},
            timeout=15,
        )
        print(f"Status: {res.status_code}")
        if res.status_code != 200:
            print("PERINGATAN: endpoint publik saja gagal diakses.")
            print("Ini kemungkinan IP VPS ini sedang diblokir Cloudflare, BUKAN masalah API key.")
            print("Coba ulangi beberapa menit lagi.")
            print()
            print("Body (potongan):")
            print(res.text[:500])
            print()
        else:
            print("OK - endpoint publik bisa diakses normal dari jaringan ini.")
        print()
    except Exception as e:
        print(f"Gagal konek sama sekali ke safetrade.com: {e}")
        sys.exit(1)

    # 1. Coba tiap variasi signing ke tiap endpoint saldo
    variants = build_variants()

    for variant in variants:
        signature = sign(API_SECRET, variant["payload"])
        headers = headers_for(variant["headers_style"], API_KEY, variant["nonce"], signature)

        for ep in BALANCE_ENDPOINTS:
            url = BASE_URL + ep
            print(f"-- Mencoba: {variant['name']}  |  endpoint: {ep} --")
            try:
                res = requests.get(url, headers=headers, timeout=15)
                print(f"   Status: {res.status_code}")
                if res.status_code == 200:
                    print("   SUKSES! Response JSON:")
                    try:
                        data = res.json()
                        print(json.dumps(data, indent=2)[:2000])
                    except Exception:
                        print(res.text[:1000])
                    print()
                    print("=" * 70)
                    print(f"SKEMA YANG BERHASIL: {variant['name']}, endpoint {ep}")
                    print("=" * 70)
                    sys.exit(0)
                else:
                    # tampilkan sedikit body untuk diagnosa (kecuali halaman HTML Cloudflare penuh)
                    body = res.text.strip()
                    if body.startswith("<!DOCTYPE") or body.startswith("<html"):
                        if "Cloudflare" in body or "cloudflare" in body:
                            print("   -> Diblokir Cloudflare (bukan error dari aplikasi SafeTrade)")
                        else:
                            print("   -> Response HTML (bukan JSON), kemungkinan diblokir WAF/redirect")
                    else:
                        print(f"   Body: {body[:500]}")
            except Exception as e:
                print(f"   Error request: {e}")
            print()

    print("=" * 70)
    print("TIDAK ADA SKEMA YANG BERHASIL.")
    print("Kemungkinan penyebab:")
    print("  1. IP VPS ini sedang diblokir Cloudflare (lihat sanity check di atas)")
    print("  2. API key/secret salah atau belum aktif")
    print("  3. Permission API key tidak mengizinkan akses endpoint ini")
    print("  4. SafeTrade pakai skema signing berbeda dari yang dicoba di sini")
    print("=" * 70)


if __name__ == "__main__":
    main()
