# vrp_dispatch_optimizer

MVP full stack untuk optimisasi dispatch distribusi BBM dari depot ke SPBU. Aplikasi ini menghitung kebutuhan truck minimum, komposisi tipe truck yang optimal, assignment order ke truck, urutan rute, total biaya, dan daftar order yang tidak terlayani bila infeasible.

## 1. Konteks bisnis

Distribusi BBM harian memiliki loading order ke banyak SPBU dengan demand, time window, dan aturan kompatibilitas kendaraan yang berbeda. Perusahaan perlu menjawab secara cepat:

- berapa truck minimum yang perlu dioperasikan
- tipe truck apa yang paling optimal
- bagaimana rute dan assignment order
- order mana yang tidak terlayani jika ada constraint yang saling bertabrakan

MVP ini fokus pada dispatch harian dan estimasi requirement armada. Master data SPBU, depot, dan network diasumsikan berasal dari service eksternal.

## 2. Tujuan aplikasi

- meminimalkan jumlah truck aktif
- meminimalkan biaya distribusi berbasis fixed cost, jarak, dan waktu
- menjaga pemenuhan demand sebisa mungkin
- menghormati time window, policy akses node, dan batas operasi kendaraan
- memberi kontrol hard constraint dan soft constraint kepada user operasional

## 3. Arsitektur singkat

- `backend/`: FastAPI, SQLAlchemy, Alembic, httpx, Google OR-Tools
- `frontend/`: React, Vite, TypeScript, Tailwind, TanStack Query, React Hook Form, Zod
- `db/`: PostgreSQL
- runtime lokal via `docker-compose`

Alur utama:

1. User input order, truck, dan constraint di web.
2. Backend merge request config dengan default global settings.
3. Preprocessing mengambil master data dan matriks network dari service eksternal atau mock mode.
4. OR-Tools routing solver mencari kombinasi truck dan rute terbaik.
5. Hasil disimpan ke PostgreSQL dan ditampilkan kembali di frontend.

## 4. Batasan MVP

- horizon 1 hari
- 1 depot per optimisasi
- semua truck dianggap kompatibel dengan semua produk supported
- setiap node SPBU dapat membatasi `truck_category` maksimum yang boleh masuk
- multi-trip didukung selama total route masih memenuhi batas working time, route duration, dan distance per vehicle
- satu shipment hanya boleh membawa satu produk untuk satu compartment
- dalam satu trip, satu compartment hanya boleh dipakai untuk satu shipment; truck harus reload ke depot sebelum memakai compartment yang sama lagi
- assignment compartment masih dimodelkan implisit lewat split shipment per kapasitas compartment dan count shipment per compartment, belum sampai mapping compartment fisik per stop di solver
- antrean depot sudah dibatasi oleh kapasitas bay (`gate_limit`) sebagai resource loading bersama, tetapi identitas bay fisik per truck belum diekspos ke output
- jendela operasi depot mengikuti `tw_start` dan `tw_end` node depot dari SPBU network master data, belum ada override manual TW depot per skenario
- belum ada driver scheduling
- belum ada visualisasi peta
- split delivery dilakukan di preprocessing bila demand order melebihi kapasitas compartment feasible terbesar

## 5. Struktur project

```text
vrp_dispatch_optimizer/
  backend/
  frontend/
  docker-compose.yml
  README.md
```

## 6. Setup lokal

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Konfigurasi PostgreSQL existing di host machine:

- Host: `localhost:5432`
- Database: `vrp_planner`
- User: `vrp_user`
- Password: `change_me`

Untuk backend yang berjalan langsung di host, gunakan:

```env
DATABASE_URL=postgresql+psycopg2://vrp_user:change_me@localhost:5432/vrp_planner
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## 7. Setup Docker

Semua service dapat dijalankan dengan:

```bash
cp .env.example .env
docker-compose up --build
```

Default `docker-compose` pada project ini memakai PostgreSQL existing di host machine, jadi backend container diarahkan ke:

```env
DATABASE_URL=postgresql+psycopg2://vrp_user:change_me@host.docker.internal:5432/vrp_planner
```

Karena backend berjalan di dalam container, `localhost` tidak boleh dipakai untuk koneksi ke database host. Gunakan `host.docker.internal`.

Jika ingin tetap menyalakan PostgreSQL container lokal terpisah, jalankan profile `local-db`:

```bash
docker-compose --profile local-db up --build
```

Secara default profile ini memetakan PostgreSQL container ke port host `5433` agar tidak bentrok dengan PostgreSQL existing di `localhost:5432`.

Service yang tersedia:

- frontend: [http://localhost:3000](http://localhost:3000)
- backend: [http://localhost:8080](http://localhost:8080)
- postgres existing host: `localhost:5432`
- postgres container opsional: `localhost:5433`

## 8. Migration

Menjalankan migration manual:

```bash
cd backend
alembic upgrade head
```

Membuat migration baru:

```bash
cd backend
alembic revision --autogenerate -m "your message"
```

## 9. Menjalankan backend dan frontend tanpa Docker

```bash
# Terminal 1
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Terminal 2
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

Untuk akses dari device lain di jaringan lokal, buka frontend lewat IP host misalnya
`http://192.168.100.219:3000`. Frontend akan otomatis mencoba backend di host yang sama
dengan port `8080`, sehingga backend perlu tetap dijalankan dengan `--host 0.0.0.0`.

Jika butuh memaksa alamat backend tertentu, set `VITE_API_BASE_URL`, misalnya:

```bash
VITE_API_BASE_URL=http://192.168.100.219:8080 npm run dev -- --host 0.0.0.0 --port 3000
```

## 10. Integrasi external API

Default base URL backend:

- non-Docker/local external app: `http://localhost:8000`
- default containerized integration: `http://host.docker.internal:8000`

Path yang dikonsumsi backend:

- `GET /api/spbu`
- `GET /api/spbu/{id}`
- `GET /api/depots`
- `GET /api/network/time-matrix`
- `GET /api/network/distance-matrix`

Path-path ini configurable via environment variable pada backend config.

## 11. Mock mode

Jika service eksternal belum tersedia, aktifkan:

```env
USE_MOCK_MASTER_DATA=true
```

Mock mode menyediakan depot, SPBU, dan matriks network sintetis berbasis koordinat mock.

## 12. Panduan objective, parameter, dan constraint

Bagian ini ditujukan sebagai petunjuk user operasional saat mengisi form optimisasi.

### Objective

- `Minimize truck count`
  Arti: mendorong solver memakai jumlah truck aktif sesedikit mungkin.
  Kapan dipakai: saat target utama adalah efisiensi armada dan pengurangan jumlah kendaraan keluar depot.

- `Minimize distance`
  Arti: mendorong solver memilih kombinasi route dengan total km lebih kecil.
  Kapan dipakai: saat biaya perjalanan per km menjadi fokus utama.

- `Minimize truck time`
  Arti: mendorong solver memilih route dengan total waktu perjalanan truck lebih kecil.
  Kapan dipakai: saat ingin menekan durasi perjalanan di jalan.

### Parameter utama skenario

- `dispatch_date`
  Tanggal operasi dispatch yang akan dihitung.

- `depot_id`
  Depot asal untuk seluruh truck pada satu skenario.

- `depot_service_time_minutes`
  Waktu loading per truck di depot sebelum truck boleh `gate out`.

- `orders[].order_id`
  ID unik order atau demand harian.

- `orders[].spbu_id`
  SPBU tujuan order.

- `orders[].product_type`
  Jenis produk BBM yang diminta order.

- `orders[].demand_kl`
  Volume demand dalam KL.

- `orders[].priority`
  Jika `true`, order dianggap prioritas dan ETA wajib diisi.

- `orders[].eta`
  Batas target kedatangan untuk order prioritas. Dipakai oleh constraint `SPBU Priority`.

- `orders[].service_time_minutes`
  Durasi bongkar atau service di SPBU untuk order tersebut.

- `orders[].time_window_start` dan `orders[].time_window_end`
  Saat ini disimpan untuk snapshot request dan tampilan input. Constraint `Time window SPBU` yang dipakai solver tetap berasal dari `tw_start` dan `tw_end` node SPBU pada master data.

- `available_trucks[].truck_id`
  ID unik truck yang tersedia pada hari dispatch.

- `available_trucks[].truck_type`
  Nama tipe truck.

- `available_trucks[].truck_category`
  Kategori akses truck. Truck hanya boleh masuk node jika `truck.truck_category <= spbu.truck_category`.

- `available_trucks[].compartments`
  Daftar compartment truck. Total kapasitas truck adalah jumlah semua compartment.

- `available_trucks[].shift_start` dan `available_trucks[].shift_end`
  Jam kerja truck.

- `available_trucks[].fixed_cost`
  Biaya tetap penggunaan truck.

- `available_trucks[].variable_cost_per_km`
  Biaya variabel per km.

- `available_trucks[].variable_cost_per_minute`
  Biaya variabel per menit perjalanan.

### Parameter batas operasional

- `max_route_duration_minutes`
  Batas total durasi route satu truck dari keluar depot sampai selesai route.

- `max_vehicle_working_time_minutes`
  Batas akumulasi jam kerja truck pada satu hari dispatch.

- `max_total_distance_per_vehicle_km`
  Batas total jarak per truck.

### Parameter penalty dan solver

- `unserved_order_penalty`
  Penalti untuk setiap shipment yang tidak terlayani saat `Allow unserved` aktif.

- `late_arrival_penalty_per_minute`
  Penalti per menit keterlambatan terhadap `TW End` SPBU master data saat `Time window SPBU` dipakai sebagai soft constraint.

- `priority_eta_penalty_per_minute`
  Penalti per menit keterlambatan terhadap ETA order prioritas saat `SPBU Priority` dipakai sebagai soft constraint.

- `overtime_penalty_per_minute`
  Penalti per menit pelanggaran `Max route duration` atau `Max working time` bila dipakai sebagai soft constraint.

- `depot_operation_window_penalty_per_minute`
  Penalti per menit pelanggaran jendela operasi depot bila `Depot operation window` dipakai sebagai soft constraint.

- `capacity_violation_penalty`
  Saat ini hanya disimpan untuk roadmap. Solver MVP masih memperlakukan kapasitas sebagai hard constraint.

- `fixed_cost_vehicle`
  Bobot tambahan fixed cost kendaraan saat `Minimize truck count` aktif.

- `distance_weight`
  Bobot objective jarak saat `Minimize distance` aktif.

- `time_weight`
  Bobot objective waktu saat `Minimize truck time` aktif.

- `solver_options.max_solver_seconds`
  Batas waktu pencarian solver.

- `solver_options.first_solution_strategy`
  Strategi solusi awal OR-Tools.

- `solver_options.local_search_metaheuristic`
  Strategi perbaikan solusi setelah solusi awal ditemukan.

### Hard constraint

- `Capacity limit`
  Truck tidak boleh melayani lebih dari kapasitas totalnya dan tidak boleh memakai compartment melebihi jumlah yang tersedia pada satu trip.

- `Time window SPBU`
  Waktu kedatangan ke SPBU wajib berada di dalam `TW Start/TW End` node SPBU dari master data.

- `SPBU Priority`
  Untuk order dengan `priority = true`, ETA wajib dipenuhi sebagai batas kedatangan keras.

- `Truck category`
  Truck hanya boleh masuk SPBU bila `truck.truck_category <= spbu.truck_category`.

- `No split order`
  Order tidak boleh dipecah menjadi beberapa shipment. Jika demand lebih besar dari kapasitas compartment feasible terbesar, order akan infeasible.

- `Depot operation window`
  Awal service depot pertama dan akhir service depot terakhir wajib berada di dalam `TW Start/TW End` node depot dari master data.

- `Max route duration`
  Route truck wajib selesai sebelum batas durasi route.

- `Max working time`
  Jam kerja truck wajib selesai sebelum batas working time.

- `Max distance per vehicle`
  Total km truck wajib di bawah batas jarak maksimum.

### Soft constraint

- `Allow unserved`
  Solver boleh meninggalkan shipment tidak terlayani dengan penalti.

- `Time window SPBU`
  Solver boleh datang lewat `TW End` node SPBU, tetapi setiap menit keterlambatan dikenai `late_arrival_penalty_per_minute`. Tidak ada input nilai tambahan karena jendela waktunya langsung mengikuti master data SPBU.

- `SPBU Priority`
  Solver boleh melewati ETA order prioritas, tetapi setiap menit keterlambatan dikenai `priority_eta_penalty_per_minute`.

- `Depot operation window`
  Operasi depot boleh melewati jendela waktu depot master data, tetapi ada penalti per menit.

- `Max route duration`
  Route boleh melebihi batas durasi, tetapi ada penalti per menit.

- `Max working time`
  Truck boleh melebihi batas working time, tetapi ada penalti per menit.

- `Max distance per vehicle`
  Truck boleh melebihi batas jarak, tetapi ada penalti.

- `Capacity limit`
  Opsi soft capacity saat ini masih roadmap. Solver MVP tetap memperlakukan kapasitas sebagai hard constraint walaupun penalty field tersedia.

## 13. OR-Tools approach

Implementasi solver menggunakan:

- `RoutingIndexManager`
- `RoutingModel`
- capacity dimension
- time dimension
- distance dimension
- vehicle fixed cost
- optional visit via disjunction penalty

Objective praktis untuk MVP:

- fixed cost kendaraan dipakai untuk mendorong minimisasi jumlah truck aktif
- arc cost menggunakan komponen jarak dan waktu sesuai bobot config
- lateness, overtime, dan pelanggaran depot operation window dipenalti sebagai soft bound bila opsinya aktif

Aturan antrean depot yang dipakai saat ini:

- `gate_limit` depot diambil dari master data node depot dan diperlakukan sebagai jumlah truck maksimum yang bisa loading bersamaan
- `tw_start` dan `tw_end` depot diambil dari master data node depot dan dipakai sebagai jendela operasi loading depot
- `depot_service_time_minutes` diisi user pada Header Dispatch sebagai durasi service/loading per truck di depot
- setiap truck aktif membuat interval `Depot Service` berdurasi tetap dan interval ini hanya dihitung bila truck benar-benar dipakai solver
- semua interval `Depot Service` dibatasi constraint `Cumulative` dengan kapasitas `gate_limit`, sehingga paling banyak `gate_limit` truck bisa loading bersamaan
- solver menambahkan node reload depot opsional di tengah route agar truck dapat kembali ke depot, mengisi ulang, lalu berangkat lagi pada trip berikutnya
- reload depot mereset kapasitas truck dan memakai resource gate yang sama dengan service awal di depot
- jika `depot_operation_window` aktif sebagai hard constraint, awal service depot pertama dan akhir service depot terakhir wajib berada di dalam TW depot
- jika `depot_operation_window` aktif sebagai soft constraint, pelanggaran awal atau akhir operasi depot tetap boleh terjadi tetapi dihitung penalty per menit
- truck boleh `gate out` lebih awal lalu menunggu keperluan time window SPBU, tetapi antrean depot hanya terjadi jika resource bay sudah penuh
- `origin_service_start` pada hasil route adalah awal service di depot, sedangkan `origin_etd` adalah waktu truck selesai service dan mulai berangkat ke SPBU

## 14. API utama

### Health

- `GET /health`

### Settings

- `GET /api/v1/settings`
- `PUT /api/v1/settings`

### Optimization

- `POST /api/v1/optimize`
- `GET /api/v1/optimize/{scenario_id}`

### Scenario

- `GET /api/v1/scenarios`
- `GET /api/v1/scenarios/{scenario_id}`
- `GET /api/v1/scenarios/{scenario_id}/routes`
- `GET /api/v1/scenarios/{scenario_id}/truck-summary`

### Master data proxy

- `GET /api/v1/master-data/spbu`
- `GET /api/v1/master-data/depots`
- `GET /api/v1/master-data/trucks`

## 15. Contoh request optimize

```json
{
  "dispatch_date": "2026-02-10",
  "depot_id": "DPT001",
  "depot_service_time_minutes": 30,
  "orders": [
    {
      "order_id": "ORD001",
      "spbu_id": "SPBU001",
      "product_type": "PERTALITE",
      "demand_kl": 16,
      "priority": true,
      "eta": "08:00",
      "service_time_minutes": 30,
      "time_window_start": "08:00",
      "time_window_end": "15:00"
    },
    {
      "order_id": "ORD002",
      "spbu_id": "SPBU002",
      "product_type": "PERTALITE",
      "demand_kl": 8,
      "priority": false,
      "eta": null,
      "service_time_minutes": 25,
      "time_window_start": "09:00",
      "time_window_end": "16:00"
    }
  ],
  "available_trucks": [
    {
      "truck_id": "TRK001",
      "truck_type": "SMALL",
      "truck_category": 2,
      "capacity_kl": 8,
      "compartments": [
        {
          "compartment_id": "C1",
          "capacity_kl": 8
        }
      ],
      "fixed_cost": 1000,
      "variable_cost_per_km": 10,
      "variable_cost_per_minute": 2,
      "start_depot_id": "DPT001",
      "end_depot_id": "DPT001",
      "shift_start": "06:00",
      "shift_end": "18:00",
      "compatible_product_types": [
        "PERTALITE",
        "PERTAMAX",
        "PERTAMAX_TURBO",
        "PERTAMAX_GREEN",
        "BIO_SOLAR",
        "DEXLITE",
        "PERTAMINA_DEX"
      ]
    },
    {
      "truck_id": "TRK002",
      "truck_type": "MEDIUM",
      "truck_category": 3,
      "capacity_kl": 16,
      "compartments": [
        {
          "compartment_id": "C1",
          "capacity_kl": 8
        },
        {
          "compartment_id": "C2",
          "capacity_kl": 8
        }
      ],
      "fixed_cost": 1800,
      "variable_cost_per_km": 12,
      "variable_cost_per_minute": 2,
      "start_depot_id": "DPT001",
      "end_depot_id": "DPT001",
      "shift_start": "06:00",
      "shift_end": "18:00",
      "compatible_product_types": [
        "PERTALITE",
        "PERTAMAX",
        "PERTAMAX_TURBO",
        "PERTAMAX_GREEN",
        "BIO_SOLAR",
        "DEXLITE",
        "PERTAMINA_DEX"
      ]
    }
  ],
  "optimization_config": {
    "minimize_truck_count": true,
    "minimize_distance": true,
    "minimize_time": true,
    "hard_constraints": {
      "capacity_limit": true,
      "time_window": true,
      "priority_eta": true,
      "truck_category": true,
      "no_split_order": false,
      "depot_operation_window": true,
      "max_route_duration": false,
      "max_vehicle_working_time": true,
      "max_total_distance_per_vehicle": false
    },
    "soft_constraints": {
      "allow_unserved_orders": true,
      "capacity_limit": false,
      "time_window": false,
      "priority_eta": false,
      "truck_category": false,
      "allow_overtime": true,
      "depot_operation_window": false,
      "max_route_duration": false,
      "max_vehicle_working_time": false,
      "max_total_distance_per_vehicle": false
    },
    "penalties": {
      "unserved_order_penalty": 100000,
      "late_arrival_penalty_per_minute": 100,
      "priority_eta_penalty_per_minute": 200,
      "overtime_penalty_per_minute": 50,
      "depot_operation_window_penalty_per_minute": 50,
      "capacity_violation_penalty": 0,
      "fixed_cost_vehicle": 10000,
      "distance_weight": 1,
      "time_weight": 1
    },
    "solver_options": {
      "max_solver_seconds": 30,
      "first_solution_strategy": "PATH_CHEAPEST_ARC",
      "local_search_metaheuristic": "GUIDED_LOCAL_SEARCH"
    },
    "max_route_duration_minutes": null,
    "max_vehicle_working_time_minutes": 720,
    "max_total_distance_per_vehicle_km": null
  }
}
```

## 16. Contoh response optimize

```json
{
  "scenario_id": "1f4b28e4-2ea0-42fa-8ddf-244ac25d45d0",
  "status": "feasible",
  "message": "Optimization finished.",
  "total_orders": 2,
  "total_demand": 24,
  "total_delivered_demand": 24,
  "total_unserved_orders": 0,
  "active_truck_count": 2,
  "active_truck_type_summary": [
    {
      "truck_type": "MEDIUM",
      "active_count": 1,
      "total_capacity_kl": 16
    },
    {
      "truck_type": "SMALL",
      "active_count": 1,
      "total_capacity_kl": 8
    }
  ],
  "total_distance": 92,
  "total_time": 199,
  "total_cost": 3930,
  "solver_runtime_seconds": 0.0182,
  "route_details": []
}
```

Nilai aktual dapat berbeda tergantung network matrix, constraint, dan solver randomness.

## 17. Testing

Menjalankan test backend:

```bash
cd backend
pytest
```

Cakupan test yang tersedia:

- preprocessing split, policy SPBU, dan compartment per trip
- solver feasible case
- solver infeasible case
- settings update
- optimize endpoint dan scenario detail

## 18. Roadmap fase berikutnya

- multi depot
- multi trip
- explicit compartment-to-stop assignment di solver
- explicit product-to-compartment assignment di solver
- richer truck category policy UI/visualization
- driver scheduling
- dashboard map visualization
- fleet simulation

## 19. Asumsi implementasi penting

- tidak ada auth pada MVP
- payload disimpan sebagai snapshot scenario untuk audit ringan
- hasil `total_cost` menggabungkan biaya fixed, variable, dan penalty yang terealisasi
- truck dari master data dapat membawa daftar `compartments`; `capacity_kl` truck adalah total seluruh compartment
- `compatible_product_types` truck saat ini dinormalisasi ke seluruh daftar produk supported, sehingga product compatibility tidak lagi menjadi pembatas routing
- `truck_category` dibaca dari truck master data API dan disimpan di snapshot scenario truck
- `truck_category` node dibaca dari SPBU network/master data node; jika node memiliki nilai kategori, hanya truck dengan kategori sama atau lebih kecil yang boleh masuk
- jika order di-split pada preprocessing, response route memakai shipment id seperti `ORD001#1`
- split order dihitung terhadap kapasitas compartment feasible terbesar, bukan lagi langsung terhadap kapasitas total truck
- setiap shipment mengonsumsi satu compartment pada satu trip, walaupun volume shipment lebih kecil dari kapasitas compartment
- truck wajib kembali reload ke depot sebelum dapat memakai compartment yang sama untuk shipment berikutnya
- `gate_limit` depot dibaca dari master data node depot dengan beberapa fallback field seperti `gate_limit`, `bay_count`, `gate_count`, atau jumlah item daftar bay bila API mengirim struktur list
- `tw_start` dan `tw_end` depot dibaca langsung dari node depot master data
- jika `gate_limit` tidak tersedia atau bernilai tidak valid, sistem fallback ke jumlah truck pada skenario agar antrean depot tidak membuat constraint palsu
- jika `tw_start` atau `tw_end` depot tidak tersedia, sistem fallback ke `00:00-23:59` agar depot operation window tidak membuat constraint palsu
- antrean depot dihitung hanya dari truck yang aktif di solusi, karena interval bay diikat ke `ActiveVehicleVar` solver
- multi-trip dimodelkan sebagai kunjungan ulang ke node depot reload di dalam satu route truck, sehingga batas waktu dan jarak tetap akumulatif per truck fisik
- route grafik menampilkan blok `Depot Service` sebelum perjalanan pertama untuk menunjukkan waktu loading dan efek antrean di depot
- frontend tetap mengizinkan input manual walaupun proxy master data tidak tersedia
- default `docker-compose` diasumsikan memakai PostgreSQL existing di host machine `vrp_planner`
