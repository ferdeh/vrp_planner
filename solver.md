# Solver Logic

Dokumen ini menjelaskan logika solver yang benar-benar berjalan di codebase `vrp_planner` saat ini. Fokusnya adalah:

- bagaimana request diubah menjadi model VRP
- constraint apa yang dipasang ke OR-Tools
- objective apa yang dioptimalkan
- bagaimana pipeline solve berjalan dari strict full-service sampai best-effort fallback
- rumus penalty utilisasi truck terbaru

Dokumen ini dimaksudkan sebagai referensi detail. Ringkasan tingkat tinggi tetap ada di `README.md`.

## 1. Arsitektur solver

Solver runtime sekarang bersifat hybrid:

- `OR-Tools` adalah final optimizer.
- `RouteFinder` opsional sebagai pembentuk cluster SPBU.
- `solution_validator` adalah final gatekeeper hasil.

Alur besarnya:

1. request masuk ke backend
2. backend merge config request dengan default settings
3. preprocessing membentuk canonical `PreprocessedProblem`
4. `solver_orchestrator` memutuskan apakah RouteFinder dipakai
5. bila RouteFinder aktif, backend menghasilkan cluster SPBU lalu menempelkan `cluster_id` ke node shipment
6. `OrToolsSolver` menjalankan pipeline solve
7. cluster RouteFinder ikut memengaruhi arc cost lewat `cluster_penalty(...)`
8. `result_service` membangun output dan breakdown biaya
9. `solution_validator` memvalidasi hasil akhir

## 2. Model data solver

Objek utama hasil preprocessing adalah `PreprocessedProblem`.

Komponen pentingnya:

- `orders`
- `trucks`
- `route_nodes`
- `time_matrix`
- `distance_matrix`
- `matrix_positions`
- `vehicle_min_cycle_minutes`
- `config`

`route_nodes` berisi dua jenis node:

- `shipment`
- `reload`

Node depot fisik tidak menjadi `route_node` biasa. Depot adalah node indeks `0` pada `RoutingIndexManager`.

## 3. Preprocessing

### 3.1 Validasi awal

Sebelum solver dipanggil, backend:

- memfilter truck yang tersedia pada `dispatch_date`
- memvalidasi order
- memvalidasi truck
- mengambil depot, SPBU, dan matrix dari master data/network service

### 3.2 Shipment splitting

Bila order lebih besar dari kapasitas compartment feasible terbesar, preprocessing bisa memecah order menjadi beberapa shipment, kecuali `hard_constraints.no_split_order = true`.

Rumus jumlah shipment:

`shipment_count = ceil(order_demand_kl / selected_shipment_capacity_kl)`

Setiap shipment lalu menjadi satu node `shipment`.

### 3.3 Allowed vehicles

Setiap shipment menyimpan `allowed_vehicle_indices`.

Truck dianggap compatible bila:

- kategori truck cocok dengan policy SPBU, atau
- hard `truck_category` dimatikan

Untuk hard category aktif, rule yang dipakai:

`truck.truck_category <= spbu.truck_category`

### 3.4 Estimasi minimum cycle

Preprocessing menghitung estimasi minimum cycle per truck.

Untuk satu shipment compatible:

`cycle_minutes = depot_service_time + travel(depot, spbu) + service_time_spbu + travel(spbu, depot)`

Lalu:

`vehicle_min_cycle_minutes[v] = min(cycle_minutes untuk semua shipment compatible truck v)`

Nilai ini dipakai lagi oleh objective utilisasi truck.

### 3.5 Estimasi maksimum trip

Untuk setiap truck:

`available_minutes = working_limit - shift_start`

`max_trip_count = max(1, floor(available_minutes / min_cycle_minutes))`

Reload node dibentuk hanya bila:

- truck punya shipment compatible
- `max_trip_count > 1`
- total demand melebihi total kapasitas awal armada

### 3.6 Reload node

Reload node dibentuk per vehicle, bukan global reset armada.

Setiap reload node membawa:

- `reload_capacity_kl = truck.capacity_kl`
- `reload_compartment_count = len(truck.compartments)`
- `reload_vehicle_index = vehicle yang boleh memakainya`
- `reload_trip_number`

Artinya reset kapasitas dan compartment mengikuti truck yang bersangkutan.

## 4. Routing model

Model dibangun di `build_routing_model_with_options`.

Node count:

`node_count = len(route_nodes) + 1`

Vehicle count:

`vehicle_count = len(trucks)`

Depot selalu di indeks manager `0`.

## 5. Dimensi kapasitas

Ada dua dimensi utama untuk resource trip:

- `Capacity`
- `Compartments`

### 5.1 Capacity dimension

Unary transit callback:

- shipment: `+ demand_kl`
- reload: `- reload_capacity_kl`

Di implementasi solver, unit disimpan dalam liter-scaled integer:

`capacity_units = round(kl * 1000)`

Jadi:

- shipment memberi beban positif
- reload mengurangi beban, sehingga muatan reset untuk trip berikutnya

### 5.2 Compartments dimension

Unary transit callback:

- shipment: `+1`
- reload: `- reload_compartment_count`

Ini memaksa satu trip tidak memakai jumlah shipment melebihi jumlah compartment aktif truck, lalu reset kembali saat reload.

## 6. Dimensi jarak

`Distance` dimension memakai callback:

`distance(from, to) = distance_matrix[from_name][to_name]`

Jika hard `max_total_distance_per_vehicle` aktif:

`Distance.End(v) <= max_total_distance_per_vehicle_km`

Jika soft aktif:

`Distance.End(v)` diberi `SoftUpperBound`.

## 7. Dimensi waktu

`Time` dimension memakai callback:

`time(from, to) = service_time(from_node) + travel_time(from, to)`

Horizon default:

`48 jam = 24 * 60 * 2`

### 7.1 Start and end time vehicle

Untuk truck `v`:

- `Start_v` dibatasi dalam `shift_start .. shift_end`
- `End_v` dibatasi oleh policy jam kerja

Working limit:

`working_limit_v = min(shift_end_v, shift_start_v + max_vehicle_working_time_minutes)`

jika `max_vehicle_working_time_minutes` diisi. Kalau tidak, `working_limit_v = shift_end_v`.

### 7.2 Hard and soft working time

Jika hard `max_vehicle_working_time` aktif:

`End_v <= working_limit_v`

Jika hard tidak aktif dan soft/overtime aktif:

`End_v` diberi `SoftUpperBound(working_limit_v, overtime_penalty_per_minute)`

### 7.3 Hard and soft route duration

Jika hard `max_route_duration` aktif:

`End_v <= shift_start_v + max_route_duration_minutes`

Jika soft aktif:

`End_v` diberi `SoftUpperBound(shift_start_v + max_route_duration_minutes, overtime_penalty_per_minute)`

## 8. Time window shipment

Untuk setiap shipment `i`:

`arrival_i = Time.CumulVar(i)`

Batas bawah selalu dipasang:

`arrival_i >= time_window_start_i`

Hard upper bound dibentuk dari kombinasi constraint aktif:

- `time_window_end`
- `priority_eta_minutes`

Jika hard `time_window` aktif:

`arrival_i <= time_window_end_i`

Jika hard `priority_eta` aktif dan shipment priority:

`arrival_i <= priority_eta_i`

Kalau dua-duanya aktif:

`arrival_i <= min(time_window_end_i, priority_eta_i)`

Jika hard `time_window` mati dan soft `time_window` aktif:

`SoftUpperBound(arrival_i, time_window_end_i, late_arrival_penalty_per_minute)`

## 9. Priority ETA soft penalty

Jika:

- `soft_constraints.priority_eta = true`
- `hard_constraints.priority_eta = false`

maka solver menambah objective lateness:

`priority_eta_lateness_i = max(0, arrival_i - priority_eta_i)`

Biaya:

`priority_eta_penalty_i = priority_eta_lateness_i * priority_eta_penalty_per_minute`

Penalty ini dimasukkan sebagai `extra_objective_var`.

## 10. Depot gate dan depot operation window

Initial loading dan reload memakai interval service depot berdurasi `depot_service_time_minutes`.

Semua interval tersebut masuk ke resource kumulatif:

`sum(active depot intervals at t) <= depot_gate_limit`

Jadi depot gate menjadi shared loading resource.

### 10.1 Depot operation span

Solver juga menghitung:

- `earliest_start`
- `latest_end`

lalu:

`depot_operation_span = max(0, latest_end - earliest_start)`

Jika objective depot aktif, variable ini dimasukkan ke objective.

### 10.2 Latest route end

Khusus mode depot, solver juga menghitung:

`latest_route_end = max(End_v untuk semua vehicle)`

Variable ini juga masuk objective depot sebagai pendorong truck selesai lebih cepat secara global.

### 10.3 Hard and soft depot operation window

Jika hard aktif:

- `earliest_start >= depot_operation_window_start`
- `latest_end <= depot_operation_window_end`

Jika soft aktif:

`early_violation = max(0, depot_operation_window_start - earliest_start)`

`late_violation = max(0, latest_end - depot_operation_window_end)`

Penalty:

`(early_violation + late_violation) * depot_operation_window_penalty_per_minute`

## 11. Vehicle compatibility and optional visits

### 11.1 Allowed vehicles

Shipment dan reload node dibatasi dengan:

`routing.SetAllowedVehiclesForIndex(allowed_vehicle_indices, node_index)`

### 11.2 Optional visits

Jika `allow_unserved_orders = false`:

- shipment mandatory
- reload tetap disjunction penalty `0`

Jika `allow_unserved_orders = true`:

- shipment boleh di-drop dengan penalty `effective_unserved_penalty`
- priority shipment tetap mandatory bila hard/soft priority ETA aktif

Reload selalu boleh tidak dipakai dengan penalty `0`.

## 12. Arc cost dan fixed cost

Arc cost per vehicle:

`arc_cost = transit_cost(distance_km, travel_minutes, truck, config) + cluster_penalty`

### 12.1 Transit cost formula

Jika `minimize_distance = true`:

`distance_component = distance_km * distance_weight * objective_priority_scale("minimize_distance")`

Jika `minimize_time = true`:

`time_component = travel_minutes * time_weight * objective_priority_scale("minimize_time")`

Maka:

`transit_cost = distance_component + time_component`

### 12.2 Fixed vehicle cost

Jika `minimize_truck_count = true`:

`fixed_cost_vehicle = activation_cost_vehicle * objective_priority_scale("minimize_truck_count")`

Kalau tidak aktif:

`fixed_cost_vehicle = 0`

## 13. Objective priority scale

Objective yang aktif diambil dari:

`objective_priority` yang booleannya `true`

Skala prioritas:

`objective_priority_scale(key) = 100^(n - rank(key) - 1)`

di mana:

- `n` = jumlah objective aktif
- `rank(key)` = posisi objective dalam urutan aktif

Artinya objective di atas punya bobot leksikografis jauh lebih kuat daripada objective di bawahnya.

## 14. Objective utilisasi truck

Ini adalah perubahan terbaru pada solver.

### 14.1 Active truck idle penalty

Penalty ini aktif pada dua mode:

- `minimize_truck_count`
- `minimize_depot_operation`

Tujuannya:

- truck aktif yang selesai terlalu cepat dianggap mahal

#### Definisi threshold kerja minimum

Untuk truck `v`:

`H_v = working_limit_minutes_v`

`Cmin_v = vehicle_min_cycle_minutes_v`

`tau_v = min(H_v, max(Cmin_v, ceil(theta_idle_mode * H_v)))`

Maknanya:

- solver tidak menuntut truck menghabiskan seluruh shift
- tetapi truck aktif diharapkan minimal bekerja setara cycle minimum atau `theta_idle_mode` dari available window, mana yang lebih besar

Default `theta_idle_mode`:

- `minimize_truck_count`: `50%`
- `minimize_depot_operation`: `75%`

Kedua nilai ini bisa diubah dari UI settings maupun form scenario, dan tombol reset akan mengembalikannya ke default di atas.

#### Definisi route work

`route_work_v = (End_v - Start_v) + depot_service_time * ActiveVehicle_v`

Penambahan `depot_service_time` di sini membuat initial loading ikut dihitung sebagai kerja truck aktif.

#### Definisi idle shortfall

`idle_shortfall_v = max(0, tau_v - route_work_v)`

#### Definisi biaya idle

`idle_penalty_cost_v = idle_shortfall_v * active_truck_idle_penalty_per_minute`

Default:

- `active_truck_idle_penalty_per_minute = 4000`

#### Aktivasi per mode

- `minimize_truck_count`: aktif
- `minimize_depot_operation`: aktif

### 14.2 Unserved order penalty

Penalty ini adalah guardrail utama untuk service level.

Default:

- `unserved_order_penalty = 1,000,000,000`

Maknanya:

- solver harus menghindari drop order selama masih ada cara untuk melayani demand dengan melanggar soft constraint
- unserved baru dipakai sebagai jalan keluar saat solver tidak menemukan solusi feasible penuh
- pada phase `best-effort partial`, backend lebih dulu menetralkan penalty soft lain agar pencarian awal benar-benar fokus meminimalkan jumlah order yang di-drop

### 14.3 Unused opportunity capacity penalty

Penalty ini hanya aktif pada:

- `minimize_depot_operation`

Tujuannya:

- trip/reload yang terlanjur dijalankan tetapi kapasitasnya tidak termanfaatkan dianggap mahal
- ini menahan solver agar tidak memperpanjang aktivitas depot dengan trip yang terlalu tipis

Penalty ini sengaja dimatikan pada `minimize_truck_count`, karena pada mode itu logika bisnisnya adalah:

- kalau truck sudah aktif, dorong dia tetap bekerja
- tidak perlu memaksa setiap trip sempurna secara fill rate

#### Delivered load dimension

Solver membangun dimension tambahan:

- shipment: `+ demand_kl`
- reload: `0`
- depot: `0`

Unit internal:

`delivered_units = round(kl * 100)`

#### Reload count

Untuk vehicle `v`:

`used_reload_count_v = sum(ActiveVar(reload_node_j) untuk semua reload node milik vehicle v)`

#### Executed trips

`executed_trips_v = ActiveVehicle_v + used_reload_count_v`

Karena:

- trip pertama datang dari aktivasi vehicle
- setiap reload berarti membuka satu trip tambahan

#### Executed trip capacity

`trip_capacity_v = capacity_kl_v * executed_trips_v`

Dalam solver, ini juga disimpan dalam unit `* 100`.

#### Unused capacity

`unused_capacity_v = max(0, trip_capacity_v - delivered_load_v)`

#### Penalty cost

`unused_capacity_penalty_v = unused_capacity_v * unused_opportunity_capacity_penalty_per_kl`

Karena solver memakai integer scaling `100`, implementasi runtime memakai pembagian integer kembali ke satuan per-KL.

Default:

- `unused_opportunity_capacity_penalty_per_kl = 60000`

#### Aktivasi per mode

- `minimize_truck_count`: tidak aktif
- `minimize_depot_operation`: aktif

## 15. Objective depot

Jika `primary_objective = minimize_depot_operation` dan `minimize_depot_operation_time = true`, solver menambah dua komponen objective:

- `latest_route_end`
- `depot_operation_span`

Dengan weight:

- `latest_route_end` memakai `depot_operation_weight * 100`
- `depot_operation_span` memakai `depot_operation_weight`

Ini membuat solver lebih sensitif pada waktu selesai global daripada hanya span murni.

## 16. Cluster penalty

Jika RouteFinder cluster aktif:

- perpindahan antar shipment beda cluster kena penalty

Soft mode:

`soft_cluster_penalty = 50_000` secara default

Hard mode:

`hard_cluster_penalty = 5_000_000` secara default

Penalty hanya berlaku untuk arc:

- shipment -> shipment

bukan ke depot atau reload.

Makna mode:

- `soft`: solver diberi bias ringan agar cenderung menahan perpindahan cluster
- `hard`: solver diberi bias sangat besar agar lebih sulit menyeberang cluster

Tetapi mode `hard` saat ini tetap bukan hard constraint absolut. Implementasinya hanya mengembalikan angka penalty objective yang besar:

`cluster_penalty = hard_cluster_penalty atau soft_cluster_penalty`

Jadi cluster masih bisa “bocor” jika:

- melayani order membuat objective total lebih murah
- menghindari `unserved_order_penalty` yang jauh lebih besar
- mengurangi kebutuhan truck aktif
- atau perpindahan terjadi lewat `reload` / `depot`, karena arc itu tidak dikenai cluster penalty

### 16.1 Simulasi kecil cluster penalty

#### Simulasi A, 1 arc lintas cluster pada mode soft

Route:

`Depot -> A1(CL-001) -> A2(CL-001) -> B1(CL-002) -> Depot`

Arc yang kena cluster penalty:

- `A2 -> B1`

Perhitungan:

- base transit cost misalnya `12.000`
- `soft_cluster_penalty = 50.000`

Maka:

`arc_cost(A2, B1) = 12.000 + 50.000 = 62.000`

#### Simulasi B, 1 arc lintas cluster pada mode hard

Route sama:

`Depot -> A1(CL-001) -> A2(CL-001) -> B1(CL-002) -> Depot`

Perhitungan:

- base transit cost misalnya `12.000`
- `hard_cluster_penalty = 5.000.000`

Maka:

`arc_cost(A2, B1) = 12.000 + 5.000.000 = 5.012.000`

#### Simulasi C, pindah cluster lewat reload

Route:

`Depot -> A1(CL-001) -> Reload -> B1(CL-002) -> Depot`

Perhitungan cluster:

- `A1 -> Reload = 0` cluster penalty
- `Reload -> B1 = 0` cluster penalty

Alasannya:

- cluster penalty hanya berlaku pada `shipment -> shipment`
- `reload` bukan shipment

## 17. Pipeline solve

Solver tidak langsung menjalankan satu solve tunggal. Pipeline berbeda tergantung primary objective.

## 18. Strict full-service config

Pada tahap strict:

- `minimize_truck_count = false`
- `minimize_distance = false`
- `minimize_time = false`
- `minimize_depot_operation_time = false`
- semua soft constraint penting dimatikan
- `allow_unserved_orders = false`

Tujuannya:

- cari solusi full-service dulu
- objective biaya belum ikut bermain

## 19. Full-service pipeline untuk mode depot

Urutannya:

1. strict full-service
2. jika strict sukses, seeded refinement dengan config depot

Config refinement depot:

- `primary_objective = minimize_depot_operation`
- `minimize_truck_count = false`
- `minimize_depot_operation_time = true`
- `allow_unserved_orders = false`

Pada tahap ini objective depot dan penalty utilisasi mode depot aktif.

## 20. Full-service pipeline untuk mode truck count

Urutannya:

1. strict full-service
2. jika perlu, coba kurangi jumlah truck aktif secara bertahap
3. seeded refinement dengan config truck count

Config refinement truck count:

- `primary_objective = minimize_truck_count`
- `minimize_truck_count = true`
- `minimize_depot_operation_time = false`
- `allow_unserved_orders = false`

Pada tahap ini:

- fixed activation cost aktif
- idle penalty aktif
- unused opportunity capacity penalty mati

## 21. Best-effort partial fallback

Jika strict full-service gagal dan `Allow unserved` aktif, solver turun ke best-effort mode.

Config best-effort:

- `allow_unserved_orders = true`
- `unserved_order_penalty >= 1_000_000_000`

Maknanya:

- solver tetap boleh drop shipment
- tetapi drop harus jauh lebih mahal daripada objective lain

Setelah partial solution ditemukan, solver menjalankan beberapa tahap perbaikan:

- repair
- targeted cleanup
- forced residual insertion
- manual residual trip constructor
- seeded optimization lagi

## 22. Manual residual trip constructor

Jika local search masih buntu, solver membangun seed route residual eksplisit:

- `reload -> shipment residual`

Ini dipakai untuk memberi OR-Tools seed yang lebih operasional pada kasus multi-trip berat.

## 23. RouteFinder integration

Jika `use_routefinder = true`:

1. orchestrator membangun canonical VRP payload
2. RouteFinder dipanggil melalui `POST /routefinder/generate-clusters`
3. service RouteFinder mengelompokkan SPBU ke beberapa cluster berdasarkan demand dan kedekatan jarak
4. backend menempelkan `cluster_id` ke canonical nodes dan `PreprocessedProblem.route_nodes`
5. OR-Tools tetap menyusun assignment vehicle, multi-trip reload, dan route akhir
6. jika RouteFinder gagal, backend fallback ke `OR-Tools only`

Jadi RouteFinder tidak pernah menjadi final authority hasil.

Setting yang dipakai:

- `use_routefinder`
- `cluster_mode`
- `max_cluster_size`

Cross-cluster penalty yang dipakai solver tetap berasal dari `optimization_config.penalties`:

- `soft_cluster_penalty`
- `hard_cluster_penalty`

## 24. Result cost breakdown

Setelah solve, `result_service` menghitung biaya hasil aktual.

Komponen biaya operasional dasar:

- `activation_cost_total`
- `distance_cost_total`
- `time_cost_total`
- `depot_operation_cost_total`

Komponen penalty:

- `unserved_penalty_total`
- `late_arrival_penalty_total`
- `priority_eta_penalty_total`
- `overtime_penalty_total`
- `max_total_distance_penalty_total`
- `depot_operation_window_penalty_total`
- `active_truck_idle_penalty_total`
- `unused_opportunity_capacity_penalty_total`

Catatan:

- cluster penalty RouteFinder dipakai pada objective solver saat optimisasi
- tetapi saat ini cluster penalty belum diekspos sebagai item breakdown terpisah pada hasil API
- karena itu `total_penalty` di response tidak memasukkan komponen cross-cluster penalty sebagai baris tersendiri

### 24.1 Simulasi kecil perhitungan penalty

Bagian ini memakai angka kecil agar cara hitung penalty mudah diverifikasi manual.

#### Simulasi 1, late arrival penalty

Kondisi:

- `TW End SPBU = 10:00`
- truck tiba `10:20`
- `late_arrival_penalty_per_minute = 100`

Perhitungan:

- keterlambatan `= 20 menit`
- penalty `= 20 * 100 = 2.000`

#### Simulasi 2, priority ETA penalty

Kondisi:

- order priority punya `ETA = 09:30`
- truck tiba `09:45`
- `priority_eta_penalty_per_minute = 200`

Perhitungan:

- keterlambatan `= 15 menit`
- penalty `= 15 * 200 = 3.000`

#### Simulasi 3, overtime penalty

Kondisi:

- batas `max_vehicle_working_time = 600 menit`
- truck selesai `645 menit`
- `overtime_penalty_per_minute = 50`

Perhitungan:

- overtime `= 45 menit`
- penalty `= 45 * 50 = 2.250`

#### Simulasi 4, depot operation window penalty

Kondisi:

- depot window berakhir `18:00`
- operasi depot terakhir selesai `18:30`
- `depot_operation_window_penalty_per_minute = 50`

Perhitungan:

- pelanggaran `= 30 menit`
- penalty `= 30 * 50 = 1.500`

#### Simulasi 5, unserved penalty

Kondisi:

- ada `1` shipment tidak terlayani
- `unserved_order_penalty = 1.000.000.000`

Perhitungan:

- penalty `= 1 * 1.000.000.000`

Hasil:

- `1.000.000.000`

#### Simulasi 6, active truck idle penalty

Kondisi:

- objective utama `minimize_truck_count`
- `H_v = 600 menit`
- threshold mode truck count `= 50%`
- `Cmin_v = 240 menit`
- route kerja aktual `route_work_v = 180 menit`
- `active_truck_idle_penalty_per_minute = 4.000`

Perhitungan threshold:

- `ceil(50% * 600) = 300`
- `max(Cmin_v, 300) = 300`
- `tau_v = min(600, 300) = 300`

Perhitungan shortfall:

- `idle_shortfall_v = max(0, 300 - 180) = 120 menit`

Penalty:

- `120 * 4.000 = 480.000`

#### Simulasi 7, unused opportunity capacity penalty

Kondisi:

- objective utama `minimize_depot_operation`
- truck `16 KL`
- executed trips `= 2`
- kapasitas kesempatan total `= 32 KL`
- delivered load aktual `= 24 KL`
- `unused_opportunity_capacity_penalty_per_kl = 60.000`

Perhitungan:

- unused capacity `= 32 - 24 = 8 KL`
- penalty `= 8 * 60.000 = 480.000`

#### Simulasi 8, kenapa cluster hard masih bisa bocor

Kondisi:

- 2 cluster, satu perpindahan cluster kena `5.000.000`
- memakai 2 truck butuh tambahan activation cost besar karena objective truck count punya skala prioritas tertinggi
- selisih objective karena menyalakan 1 truck ekstra misalnya `10.000.000.000`

Perbandingan:

- patuh cluster, pakai 2 truck: tambah objective `10.000.000.000`
- bocor cluster, pakai 1 truck: tambah objective `5.000.000`

Hasil:

- solver tetap memilih route bocor karena `5.000.000` masih jauh lebih murah daripada mengaktifkan truck ekstra dalam objective lexicographic saat ini

Total:

`total_penalty = sum(seluruh penalty aktif)`

`total_cost = activation + distance + time + depot_operation + total_penalty`

## 25. Validator akhir

Setelah result dibentuk, `solution_validator` menjadi final gatekeeper.

Maknanya:

- solver menemukan assignment belum otomatis berarti scenario `feasible`
- hasil akhir masih diperiksa lagi terhadap aturan validasi

Validator sekarang sudah mengikuti mode `hard / soft / off` untuk constraint yang relevan seperti:

- `time_window`
- `priority_eta`
- `truck_category`

Jadi kombinasi:

- `hard = false`
- `soft = false`

dibaca sebagai `off`, bukan violation.

## 26. Ringkasan perilaku mode objective

### 26.1 Minimize truck count

Perilaku yang diinginkan:

- truck aktif yang terlalu cepat selesai mahal
- truck yang sudah aktif boleh tetap dipakai walau trip tidak selalu penuh

Penalty aktif:

- `active_truck_idle_penalty`

Penalty nonaktif:

- `unused_opportunity_capacity_penalty`

### 26.2 Minimize depot operation

Perilaku yang diinginkan:

- truck aktif yang terlalu cepat selesai mahal
- reload/trip tipis yang memperpanjang aktivitas depot juga mahal

Penalty aktif:

- `active_truck_idle_penalty`
- `unused_opportunity_capacity_penalty`

## 27. Catatan penting

Beberapa hal yang masih benar untuk solver saat ini:

- `capacity_limit` soft masih roadmap; solver efektif masih hard
- `truck_category` soft belum diimplementasikan sebagai true soft search cost; solver tetap membatasi akses node di preprocessing/model, tetapi validator sudah tidak lagi salah mem-fail-kan mode off
- `time_window_start` tetap enforced sebagai lower bound
- `time_window_end` bisa hard, soft, atau off
- multi-trip saat ini dimodelkan lewat reload node, bukan entitas trip terpisah

## 28. Cara membaca perilaku solver

Kalau hasil terlihat “tidak memaksimalkan jam kerja truck” atau “depot selesai terlalu cepat”, cek berurutan:

1. primary objective aktif
2. objective priority
3. apakah run full-service atau fallback partial
4. apakah idle penalty aktif
5. apakah unused opportunity capacity penalty aktif
6. apakah cluster penalty RouteFinder ikut membias keputusan

Itu biasanya sudah cukup untuk menjelaskan mayoritas perilaku route yang terlihat di UI.
