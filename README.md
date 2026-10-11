# Telaah

Research partner untuk skripsi, tesis, dan disertasi. Ia mengumpulkan artikel, membacanya ke vector DB lokal, lalu menjawab dan mencatat keputusan riset **hanya berdasarkan bukti dari artikel yang sudah terkumpul**, lengkap dengan sitasi dan nomor halaman.

- Bukti lemah, jawabannya ditolak. Tidak ada jawaban karangan.
- Setiap klaim disertai kutipan persis dari paper, dan kutipan itu diperiksa program ada di teks sumbernya.
- Percakapan, jawaban, keputusan, dan catatan tersimpan per proyek, jadi sesi bisa dilanjutkan.
- Berjalan di terminal Anda. Data riset tersimpan di komputer Anda.

## Mulai

Butuh [uv](https://docs.astral.sh/uv/) dan [API key OpenRouter](https://openrouter.ai/keys) (isi kredit beberapa dolar; model bawaan murah).

```
mkdir skripsi-saya && cd skripsi-saya
uvx telaah -p skripsi        # nama proyek bebas; data tersimpan di ./data/skripsi/
```

Pemasangan pertama beberapa menit karena membawa Chroma dan dependensinya.

Saat pertama jalan, aplikasi meminta API key OpenRouter (ketikan tersembunyi), menguji koneksinya, dan baru membuka antarmuka bila lolos.
Kunci disimpan di `~/.config/telaah/credentials.json` (izin 0600, di luar folder proyek).

```
telaah --login               # masukkan ulang kunci
telaah --logout              # hapus kunci tersimpan
telaah -p skripsi --resume   # lanjutkan sesi terakhir (atau --resume ID)
telaah -p skripsi --sesi     # daftar sesi
```

Setelah `uvx` dipakai, perintah `telaah` bisa dipasang permanen dengan `uv tool install telaah`.

## Contoh pemakaian

Ketik dengan bahasa biasa di dalam sesi:

1. `cari 5 artikel tentang graph neural network untuk peramalan lalu lintas` → setujui unduhan dan index saat ditanya.
2. `metode apa yang dipakai paper-paper ini?` → jawaban berisi klaim, kutipan, dan sitasi seperti `Cui dkk. 2019, hlm. 3`.
3. `catat keputusan: kita pakai TGC-LSTM sebagai baseline` → keputusan wajib menunjuk jawaban berbukti.
4. `/keluar` → ringkasan sesi dibuat otomatis.

Perintah: `/bantuan`, `/koleksi`, `/memori`, `/riwayat <kata>`, `/sesi`, `/proyek`, `/keluar`.
Pertanyaan di luar topik skripsi ditolak.

## Dari mana artikel diambil

| Sumber | Yang didapat |
|---|---|
| OpenAlex (bawaan) | Pencarian artikel dari semua penerbit. PDF dari salinan open access, atau pracetak arXiv bila terbitan berbayar |
| Scopus (opsional) | Pencarian lewat `ELSEVIER_API_KEY` Anda sendiri; PDF tetap lewat OpenAlex/arXiv |

- Artikel yang hanya ada di situs penerbit (tanpa salinan terbuka) **tidak diunduh otomatis**. Taruh PDF-nya sendiri di `data/<proyek>/papers/`, lalu minta index.
- PDF dari arXiv ditandai `(pracetak)` di sitasi. Nomor halaman dan isinya bisa berbeda dari versi terbitan, jadi cek sebelum mengutip di tulisan Anda.
- Telaah tidak mengunduh dari situs IEEE Xplore, karena ketentuannya melarang unduh otomatis.
- **Telusur web (tambahan):** bila jawaban dari koleksi kurang memuaskan, asisten bisa menawarkan penelusuran web lewat plugin web OpenRouter (engine Perplexity, sekitar US$0,006 per penelusuran dari kredit OpenRouter Anda; selalu meminta konfirmasi). Hasilnya ditandai `[web, bukan bukti riset]` dan hanya dipakai untuk menemukan referensi. Web tidak pernah menjadi jawaban berbukti dan tidak bisa menjadi dasar keputusan; untuk menjadikannya bukti, paper yang ditemukan harus diunduh ke koleksi.
- Pencocokan arXiv memakai judul persis dan nama belakang penulis pertama. Pracetak yang judulnya berubah saat terbit tidak ditemukan.

## Privasi

- Folder proyek (`data/<proyek>/`) berisi PDF, vector DB, dan `memory.db`. Semuanya di komputer Anda.
- **OpenRouter** menerima potongan teks paper (untuk embedding), pertanyaan Anda, dan konteks percakapan (untuk model bahasa). Baca kebijakan OpenRouter dan penyedia model bila naskah Anda sensitif.
- **Perplexity (lewat OpenRouter)** menerima kueri telusur web bila Anda menyetujuinya. Kueri disusun model dan bisa memuat istilah dari topik skripsi Anda.
- **OpenAlex, arXiv, Crossref** menerima kata kunci pencarian, judul, dan DOI artikel. **Elsevier** menerima kueri pencarian bila Scopus diaktifkan. Isi naskah dan pertanyaan Anda tidak dikirim ke mereka.
- Telaah tidak punya server sendiri dan tidak mengirim data ke pengembangnya.
- Chroma (vector DB yang dipakai) punya telemetri anonim yang menyala secara bawaan. Matikan dengan `ANONYMIZED_TELEMETRY=False` di environment.

## Batasan

- Verifikasi hanya membuktikan **kutipan benar-benar ada** di paper. Ia tidak membuktikan tafsiran model atas kutipan itu benar. Baca kutipannya.
- Pencarian bukti sensitif pada rumusan pertanyaan. Bila jawabannya "bukti tidak cukup" padahal Anda yakin ada, coba ubah kata kuncinya.
- Cakupan artikel mengikuti OpenAlex, open access, dan arXiv. Tidak semua jurnal berbayar bisa dibaca.
- Hasil model bahasa tetap perlu Anda periksa sebelum masuk ke naskah.

## Pengaturan

Opsional, lewat environment atau berkas `.env` di folder kerja (menang atas kunci tersimpan):

| Variabel | Fungsi |
|---|---|
| `OPENROUTER_API_KEY` | Kunci OpenRouter (tetap dites tiap start) |
| `OPENROUTER_CHAT_MODEL` | Model bahasa. Bawaan `deepseek/deepseek-v4.1-flash` |
| `OPENROUTER_EMBED_MODEL` | Model embedding. Bawaan `qwen/qwen3-embedding-8b`. Mengganti model pada proyek yang sudah ter-index ditolak sampai Anda menjalankan `python -m telaah.ingest -p <proyek> --reindex` |
| `ELSEVIER_API_KEY` | Mengaktifkan sumber Scopus |
| `PROJECTS_DIR` | Lokasi folder proyek. Bawaan `./data` |

## Pengembangan

```
uv venv && uv pip install -e . pytest
.venv/bin/python run.py -p uji     # atau: python -m telaah
.venv/bin/python -m pytest -q tests
uv build                            # hasil di dist/
```

Kode ada di `src/telaah/`. Modul tunggal bisa dijalankan: `python -m telaah.ingest -p skripsi`.
`tests/eval_scope.py` menguji batas topik dengan model sungguhan (jalankan manual, memakai kuota API).

## Lisensi

MIT. Lihat [LICENSE](LICENSE).
