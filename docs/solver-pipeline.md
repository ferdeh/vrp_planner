# Solver Pipeline

Dokumen ini merangkum perilaku solver terbaru pada planner backend. Fokus utamanya adalah memastikan coverage order didahulukan sebelum optimasi objective biaya, jarak, dan waktu.

## Prinsip utama

- solver selalu mencoba `full-service` lebih dulu
- `Allow unserved` bukan lagi objective, tetapi hanya izin untuk fallback ke partial solution
- partial solution tidak dicari dari nol bila sudah ada seed yang baik; solver mencoba repair dari solusi yang sudah ditemukan
- multi-trip dilakukan melalui reload depot yang dibentuk per grup truck agar reset kapasitas dan compartment sesuai tipe truck

## Tahapan solve

1. `Strict full-service`
   Solver membangun model dengan `allow_unserved_orders = false`. Semua shipment mandatory dan objective biaya utama dimatikan sementara agar pencarian fokus pada coverage.

2. `Seeded full-service optimization`
   Jika tahap strict menemukan full-service, assignment itu dipakai sebagai seed. Solver lalu mengaktifkan objective biaya, truck count, distance, time, dan depot operation time tanpa boleh drop shipment.

3. `Best-effort partial fallback`
   Jika strict full-service gagal dan `Allow unserved` aktif, solver turun ke mode partial. Shipment boleh di-drop dengan penalty sangat besar agar hasil tetap meminimalkan unserved lebih dulu.

4. `Repair dan targeted cleanup`
   Dari partial solution yang sudah ada, solver mengambil shipment residual lalu memprioritaskan truck dengan jam kerja aktual paling rendah atau slack terbaik. Tujuannya adalah menutup order sisa tanpa merombak seluruh route yang sudah bagus.

5. `Forced residual insertion`
   Jika cleanup biasa belum cukup, shipment yang sudah served dikunci ke truck asal. Search kemudian difokuskan hanya pada shipment residual agar ruang pencarian lebih sempit dan lebih agresif terhadap unserved yang tersisa.

6. `Manual residual trip constructor`
   Jika local search tetap buntu, backend membangun seed route residual secara eksplisit dengan pola `reload -> shipment residual`, lalu mengirim seed itu kembali ke OR-Tools untuk divalidasi dan disempurnakan.

7. `Final objective refinement`
   Setelah coverage terbaik ditemukan, solver menjalankan refinement akhir sesuai urutan objective user.

   Jika objective primer jatuh ke `minimize_depot_operation`, refinement ini juga mendorong span operasi depot aktual menjadi serapat mungkin agar truck pertama tidak terlalu cepat masuk loading dan truck terakhir tidak terlalu lama menutup operasi depot.

## Peran Allow unserved

- `Allow unserved = false`
  Solver hanya boleh mengembalikan hasil strict/full-service path. Jika tidak menemukan solusi full-feasible dalam budget waktu, solver tidak akan turun ke partial fallback.

- `Allow unserved = true`
  Solver tetap mencoba strict full-service terlebih dahulu. Fallback partial baru dipakai jika tahap strict gagal.

## Reload depot per grup truck

Reload depot tidak lagi memakai reset global armada. Backend sekarang membentuk reload node per grup truck, misalnya:

- truck kecil `8 KL / 1 compartment`
- truck besar `16 KL / 2 compartment`

Setiap reload node hanya boleh dipakai truck dari grup yang sesuai, dan reset kapasitas serta compartment-nya juga mengikuti grup itu. Ini penting agar truck kecil dapat melakukan multi-trip secara valid tanpa "mewarisi" reset milik truck besar.

## Implikasi operasional

- jika full-service memang feasible, solver akan berusaha mencapainya lebih dulu sebelum meminimalkan cost
- jika masih ada unserved setelah fallback, hasil itu berarti solver sudah melewati beberapa tahap repair bertingkat, bukan langsung berhenti pada partial solve pertama
- jika residual order tetap tidak bisa ditutup, penyebabnya biasanya constraint model yang benar-benar membatasi, bukan sekadar solver belum mencoba multi-trip
