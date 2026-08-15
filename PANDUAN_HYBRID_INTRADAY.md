# Panduan: Arsitektur Hybrid (Intraday Timing + Daily Confirmation)

## Konsep Dasar

Sistem sekarang memisahkan dua peran data:

| Peran | Sumber Data | Dipakai untuk |
|---|---|---|
| **TIMING** (kapan breakout terjadi) | Intraday (misal 15 menit) | Harga, titik terendah, volume per-bar |
| **KONFIRMASI** (apakah breakout ini sehat) | Harian | Tren mingguan (MTF), volatilitas (ATR), akumulasi (OBV) |

**Kenapa dipisah begini?**
- Data intraday terlalu "berisik" untuk mengukur tren besar atau akumulasi jangka menengah — sinyalnya gampang salah arah dalam hitungan menit.
- Data harian terlalu lambat untuk menangkap **momen pasti** breakout terjadi — kalau nunggu candle harian selesai, momentumnya sudah lewat.
- Kombinasi keduanya: **timing presisi + konfirmasi stabil.**

---

## Parameter Baru untuk Data Intraday

| Variable | Default | Keterangan |
|---|---|---|
| `INTRADAY_INTERVAL` | `15m` | Interval candle: `1m`, `2m`, `5m`, `15m`, `30m`, `60m`, `90m` |
| `INTRADAY_PERIOD_DAYS` | `5` | Berapa hari terakhir data intraday yang diambil |
| `INTRADAY_LOOKBACK_BARS` | `20` | Cari titik terendah dalam berapa bar intraday terakhir |
| `VOLUME_LOOKBACK_BARS` | `20` | Rata-rata volume dihitung dari berapa bar terakhir |

## Parameter Data Harian (untuk Konfirmasi)

| Variable | Default | Keterangan |
|---|---|---|
| `DAILY_PERIOD_DAYS` | `200` | Berapa hari data harian yang diambil (untuk histori MTF/ATR/OBV) |
| `MTF_SMA_WEEKS` | `10` | Periode SMA mingguan |
| `ATR_PERIOD` | `14` | Periode ATR harian |
| `OBV_SMA_PERIOD` | `20` | Periode SMA OBV harian |

---

## ⚠️ Keterbatasan Penting yang Perlu Kamu Terima

### 1. Batasan Yahoo Finance untuk Data Intraday
Data dengan interval di bawah 1 hari **hanya tersedia untuk ~60 hari terakhir** — ini batasan resmi dari Yahoo Finance, bukan bug di script kita. Untuk kebutuhan lookback pendek (20 bar), ini seharusnya lebih dari cukup.

### 2. Keandalan Data Intraday untuk Saham Indonesia (.JK)
**Ini belum saya verifikasi langsung** karena keterbatasan akses internet di sandbox saat development. Yang perlu kamu cek sendiri setelah script pertama kali jalan:
- Apakah jumlah bar yang didapat sesuai ekspektasi (misal 15 menit x jam bursa ~7,25 jam = sekitar 29 bar per hari)?
- Apakah ada gap/bar kosong yang mencurigakan (indikasi saham kurang likuid atau data tidak lengkap)?
- Cek log di tab **Actions** — kalau muncul warning "Data intraday hanya X bar, kurang dari lookback...", berarti data tidak cukup rapat.

**Kalau data intraday ternyata tidak reliable untuk saham yang kamu pantau**, opsi mundur:
- Naikkan `INTRADAY_INTERVAL` ke `30m` atau `60m` (interval lebih besar biasanya lebih konsisten datanya).
- Atau, kalau tetap bermasalah, kembali ke versi full-daily (screenshot script sebelumnya) yang sudah terbukti stabil meski timing-nya kurang presisi.

### 3. Delay Data Tetap Ada
Delay 10 menit dari yfinance (yang sudah kita bahas sebelumnya) **tetap berlaku** untuk data intraday, bukan cuma data harian. Kombinasi delay + interval cron 5 menit berarti breakout yang kamu terima notifikasinya mencerminkan kondisi sekitar 10-15 menit yang lalu — jauh lebih baik dari versi full-daily (yang bisa delay berjam-jam), tapi tetap bukan real-time murni.

### 4. Interval Cek vs Interval Candle
Kalau kamu set `INTRADAY_INTERVAL=15m` tapi cron GitHub Actions jalan tiap 5 menit, artinya **beberapa run berturut-turut akan melihat bar/candle 15 menit yang sama** sampai candle baru terbentuk. Ini normal — state management sudah menangani supaya tidak alert berulang untuk breakout dari bar yang sama.

---

## Contoh Kombinasi Konfigurasi

### Untuk Saham Likuid (TINS, ANTM, TLKM, dll)
```
INTRADAY_INTERVAL=15m
INTRADAY_PERIOD_DAYS=5
INTRADAY_LOOKBACK_BARS=20
VOLUME_MULTIPLIER=1.5
```

### Untuk Saham Kurang Likuid (kalau data 15m terlalu bolong)
```
INTRADAY_INTERVAL=30m
INTRADAY_PERIOD_DAYS=10
INTRADAY_LOOKBACK_BARS=15
VOLUME_MULTIPLIER=1.3
```

### Untuk Timing Lebih Presisi (kalau data 5m ternyata reliable)
```
INTRADAY_INTERVAL=5m
INTRADAY_PERIOD_DAYS=3
INTRADAY_LOOKBACK_BARS=30
VOLUME_MULTIPLIER=1.8
```

---

## Cara Membaca Log

```
2026-08-14 | INFO | TINS.JK | Harga: 3851 @ 2026-08-14 14:15:00 |
Low: 3736 | Trigger: 3829 | Naik: 3.08% |
Breakout harga: True | Final (semua filter): True
```

Perhatikan bagian `@ 2026-08-14 14:15:00` — ini timestamp bar intraday spesifik yang jadi acuan, bukan cuma tanggal harian. Berguna untuk cross-check manual dengan Running Trade di Stockbit pada jam yang sama.

---

## Rekomendasi Cara Mulai

1. **Jalankan dulu dengan `workflow_dispatch` manual** beberapa kali di jam bursa berbeda untuk lihat apakah data intraday konsisten untuk ticker yang kamu pantau.
2. **Cek log tiap run** — kalau sering muncul warning soal data intraday kurang, pertimbangkan naikkan interval ke `30m`.
3. **Bandingkan dengan Running Trade Stockbit** sesekali — cocokkan timestamp breakout yang terdeteksi sistem dengan apa yang sebenarnya terjadi di Running Trade pada jam yang sama, untuk membangun kepercayaan terhadap akurasi timing sistem.
