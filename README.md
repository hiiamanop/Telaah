# Telaah

Research partner pribadi untuk skripsi / tesis / disertasi. Visi: kumpulkan artikel, baca, simpan ke vector DB, lalu setiap jawaban dan keputusan riset berbasis bukti dari referensi yang terkumpul.

## Pakai

Butuh [uv](https://docs.astral.sh/uv/). Dari folder kerja skripsi Anda:

```
uvx telaah -p skripsi        # nama proyek bebas; data tersimpan di ./data/skripsi/
```

Saat pertama jalan, aplikasi meminta API key [OpenRouter](https://openrouter.ai/keys) (ketikan tersembunyi), menguji koneksinya, dan baru masuk ke antarmuka bila lolos.
Kunci disimpan di `~/.config/telaah/credentials.json` (izin 0600, di luar folder proyek). Perintah terkait:

```
telaah --login               # masukkan ulang kunci
telaah --logout              # hapus kunci tersimpan
```

Alternatif: isi `OPENROUTER_API_KEY` di `.env` folder kerja (menang atas kunci tersimpan; tetap dites tiap start). Opsional: `ELSEVIER_API_KEY` untuk sumber Scopus.
Model bahasa bawaan: `deepseek/deepseek-v4.1-flash` (ubah dengan `OPENROUTER_CHAT_MODEL`).

Dalam sesi, ketik biasa (cari artikel, index, tanya, catat keputusan) atau perintah `/bantuan`.
Lanjutkan sesi: `uvx telaah -p skripsi --resume`. Daftar sesi: `--sesi`.
Percakapan, jawaban berbukti, keputusan, dan catatan tersimpan di `data/<proyek>/memory.db`.

## Pengembangan

```
uv venv && uv pip install -e . pytest
.venv/bin/python run.py -p uji     # atau: python -m telaah
.venv/bin/python -m pytest -q tests
uv build                            # hasil di dist/
```

Kode ada di `src/telaah/`. Modul tunggal bisa dijalankan: `python -m telaah.ingest -p skripsi`.
