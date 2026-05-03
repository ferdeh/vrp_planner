import { Link } from "react-router-dom";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";

const quickSteps = [
  {
    title: "1. Pilih Header Dispatch",
    description:
      "Tentukan dispatch date, depot, dan service time per truck. Data depot dan gate diambil dari master data node depot.",
  },
  {
    title: "2. Isi Order Harian",
    description:
      "Masukkan SPBU, produk, demand, service time, dan tandai priority bila order punya ETA khusus.",
  },
  {
    title: "3. Sync Armada",
    description:
      "Gunakan Sync Truck agar armada available, truck category, dan compartment mengikuti truck master data.",
  },
  {
    title: "4. Atur Objective dan Constraint",
    description:
      "Pilih fokus optimisasi dan tentukan rule mana yang wajib keras atau boleh dilanggar dengan penalty.",
  },
  {
    title: "5. Jalankan dan Evaluasi",
    description:
      "Periksa summary scenario, route grafik, route map, depot operation, unserved order, dan compare antar scenario.",
  },
];

const objectives = [
  {
    title: "Minimize truck count",
    description:
      "Mengurangi jumlah truck aktif yang harus keluar depot setelah solver menemukan coverage order terbaik yang bisa dicapai.",
  },
  {
    title: "Minimize distance",
    description: "Mengurangi total km perjalanan seluruh truck setelah tahap full-service atau repair selesai.",
  },
  {
    title: "Minimize truck time",
    description: "Mengurangi total waktu perjalanan truck di jalan setelah coverage order terbaik ditemukan.",
  },
  {
    title: "Minimize depot operation time",
    description: "Mendorong truck gate out lebih pagi dan menyelesaikan rute lebih cepat agar operasi depot tidak molor.",
  },
];

const scenarioParameters = [
  {
    name: "Dispatch date",
    description: "Tanggal skenario yang dihitung.",
  },
  {
    name: "Depot",
    description: "Depot asal seluruh armada pada satu skenario.",
  },
  {
    name: "Service time per truck",
    description: "Durasi loading per truck di depot sebelum truck bisa gate out.",
  },
  {
    name: "Order priority",
    description: "Jika dicentang, ETA wajib diisi dan order ikut rule SPBU Priority.",
  },
  {
    name: "ETA priority",
    description: "Batas target kedatangan order priority. Jika SPBU Priority hard maka wajib tepat waktu, jika soft maka keterlambatan kena penalty.",
  },
  {
    name: "Service time order",
    description: "Durasi bongkar atau service di SPBU untuk order tersebut.",
  },
  {
    name: "Truck category",
    description: "Kategori akses truck yang dicocokkan dengan truck category node SPBU.",
  },
  {
    name: "Compartments",
    description: "Daftar compartment truck. Satu shipment mewakili satu compartment untuk satu produk per trip.",
  },
  {
    name: "Shift truck",
    description: "Jam kerja awal dan akhir truck.",
  },
];

const parameterNotes = [
  "Time window SPBU untuk solver diambil dari `tw_start` dan `tw_end` node SPBU master data.",
  "Field `time_window_start` dan `time_window_end` pada order tetap disimpan di request snapshot, tetapi bukan sumber constraint solver.",
  "Soft `Time window SPBU` tidak memerlukan input value tambahan. Sistem langsung memakai TW master data dan menghitung penalty bila terlambat.",
  "Order priority tetap wajib dilayani saat `SPBU Priority` aktif sebagai hard maupun soft. Priority baru boleh ikut `Allow unserved` bila `SPBU Priority` tidak aktif.",
  "Solver tidak lagi langsung mencampur semua objective sekaligus. Sistem sekarang mencoba strict full-service lebih dulu, lalu baru mengoptimalkan objective biaya dan efisiensi.",
];

const hardConstraints = [
  {
    title: "Capacity limit",
    description: "Truck tidak boleh melebihi kapasitas total dan tidak boleh memakai compartment melebihi jumlah yang tersedia pada satu trip.",
  },
  {
    title: "Time window SPBU",
    description: "Kedatangan truck wajib berada di dalam TW Start dan TW End node SPBU master data.",
  },
  {
    title: "SPBU Priority",
    description: "Order priority wajib dilayani dan wajib tiba sebelum atau sama dengan ETA yang diisi user.",
  },
  {
    title: "Truck category",
    description: "Truck hanya boleh masuk SPBU bila `truck_category` truck sama atau lebih kecil dari kategori node SPBU.",
  },
  {
    title: "No split order",
    description: "Order tidak boleh dipecah menjadi beberapa shipment.",
  },
  {
    title: "Depot operation window",
    description: "Operasi loading depot wajib berada di dalam TW depot dari master data.",
  },
  {
    title: "Max route duration",
    description: "Membatasi durasi total satu route truck.",
  },
  {
    title: "Max working time",
    description: "Membatasi total jam kerja truck pada satu skenario.",
  },
  {
    title: "Max distance per vehicle",
    description: "Membatasi total km per truck.",
  },
];

const softConstraints = [
  {
    title: "Allow unserved",
    description: "Shipment boleh tidak terlayani dengan penalty hanya sebagai fallback. Solver tetap mencoba full-service lebih dulu. Order priority hanya boleh ikut rule ini bila SPBU Priority tidak aktif sebagai hard maupun soft.",
  },
  {
    title: "Time window SPBU",
    description: "Truck boleh terlambat dari TW End SPBU, tetapi setiap menit terlambat kena penalty.",
  },
  {
    title: "SPBU Priority",
    description: "Order priority tetap wajib dilayani, tetapi truck boleh melewati ETA dan setiap menit terlambat kena penalty.",
  },
  {
    title: "Depot operation window",
    description: "Operasi depot boleh melanggar TW depot, tetapi ada penalty per menit.",
  },
  {
    title: "Max route duration",
    description: "Route boleh melewati batas durasi dengan penalty.",
  },
  {
    title: "Max working time",
    description: "Truck boleh melewati batas working time dengan penalty.",
  },
  {
    title: "Max distance per vehicle",
    description: "Truck boleh melewati batas km dengan penalty.",
  },
  {
    title: "Capacity limit",
    description: "Saat ini masih roadmap. Solver MVP tetap memperlakukan kapasitas sebagai hard constraint.",
  },
];

const penalties = [
  {
    name: "Unserved order penalty",
    description: "Penalty untuk shipment yang tidak terlayani saat Allow unserved aktif.",
  },
  {
    name: "Late arrival penalty per minute",
    description: "Penalty per menit untuk soft Time window SPBU.",
  },
  {
    name: "Priority ETA penalty per minute",
    description: "Penalty per menit untuk soft SPBU Priority.",
  },
  {
    name: "Overtime penalty per minute",
    description: "Penalty per menit untuk soft Max route duration atau Max working time.",
  },
  {
    name: "Depot operation window penalty per minute",
    description: "Penalty per menit untuk soft Depot operation window.",
  },
  {
    name: "Active truck idle penalty per minute",
    description: "Penalty per menit jika truck aktif selesai terlalu cepat dibanding threshold utilisasi minimum pada objective truck count atau depot operation.",
  },
  {
    name: "Unused opportunity capacity penalty per KL",
    description: "Penalty per KL untuk kapasitas trip atau reload yang terlanjur dijalankan tetapi tidak termanfaatkan. Aktif pada objective minimize depot operation time.",
  },
  {
    name: "Soft cross-cluster penalty",
    description: "Penalty perpindahan shipment ke shipment antar cluster RouteFinder saat cluster mode soft aktif.",
  },
  {
    name: "Hard cross-cluster penalty",
    description: "Penalty perpindahan shipment ke shipment antar cluster RouteFinder saat cluster mode hard aktif. Nilai ini tetap berupa objective penalty besar, bukan hard constraint absolut.",
  },
  {
    name: "Idle threshold truck count dan depot operation",
    description: "Threshold utilisasi minimum truck aktif untuk objective utama minimize truck count dan minimize depot operation time. Default masing-masing 50% dan 75%.",
  },
];

const outputs = [
  "Scenario Summary menunjukkan truck aktif, demand delivered, cost, penalty, depot operation, dan runtime.",
  "Cluster Metrics sekarang tampil di dalam tab Scenario Summary, tepat di bawah card grafik armada.",
  "Order Detail menampilkan List Order lengkap beserta status served atau unserved, ETA SPBU, dan nopol truck yang melayani.",
  "Route Grafik memperlihatkan urutan pergerakan truck termasuk Depot Service dan Depot Reload.",
  "Route Map memperlihatkan base edge masterdata dan overlay pergerakan truck per warna di atas graph node SPBU/depot.",
  "Route per MT menampilkan stop detail, ETA, ETD, volume kirim, dan trip per truck.",
  "Compare scenario memudahkan membandingkan hasil beberapa skenario pada hari yang sama.",
];

const routeFinderSettings = [
  "Semua pengaturan RouteFinder sekarang berada di halaman Settings dan Constraints, di bagian paling bawah setelah kelompok Default Cost dan Penalty.",
  "Field yang tersedia adalah Use RouteFinder Clustering, Cluster Mode, Max Cluster Size, Soft cross-cluster penalty, dan Hard cross-cluster penalty.",
  "Tombol Simpan Settings akan menyimpan settings global sekaligus solver settings RouteFinder.",
  "Tombol Reset cross-cluster penalty ke default mengembalikan nilai ke soft 50000 dan hard 5000000.",
  "RouteFinder hanya membentuk cluster SPBU. OR-Tools tetap menjadi solver final untuk assignment vehicle, multi-trip, dan route akhir.",
];

const routeMapNotes = [
  "Klik legend nopol truck untuk fokus ke satu truck dan meredupkan overlay truck lain.",
  "Klik legend `Base Edge Masterdata` untuk menyorot edge masterdata dan membuat overlay truck menjadi abu atau redup.",
  "Gunakan scroll mouse atau gesture trackpad Mac untuk zoom in / zoom out.",
  "Gunakan drag pada area map untuk pan ke area graph yang berbeda.",
];

const solverStages = [
  {
    title: "Stage 1, strict full-service",
    description: "Solver terlebih dahulu mencoba solusi yang melayani semua shipment dengan `Allow unserved` dimatikan secara internal.",
  },
  {
    title: "Stage 2, seeded full-service optimization",
    description: "Jika full-service ditemukan, solusi itu dipakai sebagai seed untuk mengoptimalkan truck count, distance, time, dan depot operation time tanpa boleh drop order.",
  },
  {
    title: "Stage 3, best-effort partial fallback",
    description: "Jika strict full-service gagal dan `Allow unserved` aktif, solver turun ke mode partial dengan penalty unserved sangat besar.",
  },
  {
    title: "Stage 4, repair dan residual cleanup",
    description: "Dari solusi partial yang sudah ada, solver mencoba targeted cleanup, forced residual insertion, dan repair tambahan untuk menutup order sisa sebelum menerima partial akhir.",
  },
];

const fallbackNotes = [
  "Objective `Minimize unserved orders` sudah tidak dipakai lagi. Coverage order sekarang ditentukan oleh pipeline solver, bukan toggle objective terpisah.",
  "Jika `Allow unserved` aktif, solver tetap mencoba strict full-service terlebih dahulu. Partial fallback baru dipakai jika tahap itu gagal.",
  "Jika `Allow unserved` nonaktif dan strict full-service gagal atau timeout, backend tidak turun ke partial fallback.",
];

const scenarioAnalysisLevels = [
  {
    title: "Level 1, cepat",
    description:
      "Memakai heuristik dari hasil scenario existing tanpa rerun solver. Cocok untuk triage cepat dengan respons ringan.",
    points: [
      "Menggunakan hasil scenario yang sudah ada, termasuk status solver, unserved order, cluster priority, dan travel time direct depot ke SPBU.",
      "Menampilkan Root Cause Summary, Solver Status Explained, Key Findings, Recommended Actions, dan ranking order paling problematik.",
      "Paling cocok saat user butuh analisis cepat tanpa beban komputasi tambahan.",
    ],
  },
  {
    title: "Level 2, kuat",
    description:
      "Menjalankan worker diagnosis terpisah yang melakukan beberapa rerun otomatis untuk menguji akar masalah scenario secara lebih akurat.",
    points: [
      "Eksperimen diagnosis mencakup extended timeout, priority only, priority ETA disabled, dan allow unserved on.",
      "Hasil eksperimen diubah menjadi insight bisnis lewat inference engine, bukan hanya angka teknis solver.",
      "Paling cocok untuk scenario timeout, infeasible, atau investigasi mendalam sebelum mengubah constraint operasional.",
    ],
  },
];

const scenarioAnalysisOutputs = [
  "Root Cause Summary merangkum akar masalah skenario dalam bahasa bisnis.",
  "Solver Status Explained menjelaskan arti status seperti feasible, partial, timeout, dan infeasible.",
  "Key Findings menyorot temuan paling penting dari scenario atau eksperimen diagnosis.",
  "Recommended Actions memberi arah tindak lanjut yang bisa dicoba user.",
  "Ranking Order Paling Problematik menunjukkan order yang paling besar kontribusinya terhadap kesulitan skenario.",
];

function GuideSection({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel overflow-hidden">
      <div className="panel-body space-y-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">{eyebrow}</p>
          <h2 className="mt-3 text-2xl font-semibold text-ink">{title}</h2>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">{description}</p>
        </div>
        {children}
      </div>
    </section>
  );
}

export function UserGuidePage() {
  return (
    <AppLayout>
      <PageHeader
        title="Panduan User"
        description="Petunjuk penggunaan VRP Planner untuk operator dispatch, planner, dan analyst operasional."
        action={
          <Link className="btn-primary" to="/new-optimization">
            Buka Form Optimisasi
          </Link>
        }
      />

      <GuideSection
        eyebrow="Quick Start"
        title="Alur Penggunaan"
        description="Urutan kerja yang direkomendasikan agar input skenario lengkap dan hasil optimisasi lebih mudah dibaca."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {quickSteps.map((item) => (
            <article key={item.title} className="rounded-[24px] border border-slate-200 bg-slate-50/80 p-5">
              <h3 className="text-base font-semibold text-ink">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
            </article>
          ))}
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Objectives"
        title="Arti Objective"
        description="Objective menentukan preferensi biaya solver. Anda dapat menyalakan lebih dari satu objective sekaligus dan mengubah urutannya dengan drag and drop. Urutan paling atas akan diprioritaskan lebih dulu."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          {objectives.map((item) => (
            <article key={item.title} className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-semibold text-ink">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
            </article>
          ))}
        </div>
        <div className="rounded-[24px] border border-sky-200 bg-sky-50/80 p-5">
          <h3 className="text-base font-semibold text-sky-950">Catatan prioritas objective</h3>
          <p className="mt-2 text-sm leading-6 text-sky-900">
            Walaupun urutan objective tetap dibaca dari atas ke bawah, solver sekarang selalu mencoba full-service
            lebih dulu. Objective biaya dan efisiensi baru dioptimalkan setelah coverage terbaik ditemukan.
          </p>
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Solver Flow"
        title="Cara Solver Bekerja"
        description="Backend sekarang memakai multi-stage solve agar perilaku lebih dekat ke operasi nyata. Solver tidak langsung mengejar route yang murah, tetapi lebih dulu mencoba memenuhi seluruh order."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {solverStages.map((item) => (
            <article key={item.title} className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-ink">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
            </article>
          ))}
        </div>
        <div className="rounded-[24px] border border-amber-200 bg-amber-50/90 p-5">
          <h3 className="text-base font-semibold text-amber-950">Best-effort fallback</h3>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-amber-900">
            {fallbackNotes.map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Inputs"
        title="Parameter yang Diisi User"
        description="Parameter berikut paling sering diisi atau ditinjau oleh user saat membuat skenario baru."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {scenarioParameters.map((item) => (
            <article key={item.name} className="rounded-[22px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-ink">{item.name}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
            </article>
          ))}
        </div>
        <div className="rounded-[24px] border border-sky-200 bg-sky-50/80 p-5">
          <h3 className="text-base font-semibold text-sky-950">Catatan penting</h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-sky-950/80">
            {parameterNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Constraints"
        title="Hard Constraint"
        description="Hard constraint wajib dipenuhi. Jika bertabrakan, solver bisa menghasilkan scenario infeasible atau order menjadi unserved sesuai pengaturan."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {hardConstraints.map((item) => (
            <article key={item.title} className="rounded-[22px] border border-emerald-200 bg-emerald-50/60 p-5">
              <h3 className="text-base font-semibold text-emerald-950">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-emerald-950/80">{item.description}</p>
            </article>
          ))}
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Constraints"
        title="Soft Constraint"
        description="Soft constraint boleh dilanggar, tetapi ada konsekuensi penalty di objective. Gunakan jika Anda ingin hasil tetap keluar walaupun ada konflik operasional."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {softConstraints.map((item) => (
            <article key={item.title} className="rounded-[22px] border border-amber-200 bg-amber-50/70 p-5">
              <h3 className="text-base font-semibold text-amber-950">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-amber-950/80">{item.description}</p>
            </article>
          ))}
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Penalties"
        title="Parameter Penalty"
        description="Penalty menentukan seberapa mahal pelanggaran soft constraint dibanding biaya route normal."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {penalties.map((item) => (
            <article key={item.name} className="rounded-[22px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-ink">{item.name}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
            </article>
          ))}
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Settings"
        title="RouteFinder Settings"
        description="Pengaturan hybrid RouteFinder sekarang tidak lagi berada di tab terpisah. Semua field solver settings dipusatkan ke halaman Settings global."
      >
        <div className="rounded-[24px] border border-slate-200 bg-white p-6 shadow-sm">
          <ul className="list-disc space-y-3 pl-5 text-sm leading-6 text-slate-600">
            {routeFinderSettings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Outputs"
        title="Cara Membaca Hasil"
        description="Halaman scenario detail dan compare memberikan beberapa sudut pandang hasil optimisasi."
      >
        <div className="rounded-[24px] border border-slate-200 bg-white p-6 shadow-sm">
          <ul className="list-disc space-y-3 pl-5 text-sm leading-6 text-slate-600">
            {outputs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-[24px] border border-sky-200 bg-sky-50/80 p-5">
          <h3 className="text-base font-semibold text-sky-950">Interaksi Route Map</h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-sky-950/80">
            {routeMapNotes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </GuideSection>

      <GuideSection
        eyebrow="Scenario Analysis"
        title="Level Analysis"
        description="Scenario Analysis membantu user mendiagnosis akar masalah skenario. Fitur ini terpisah dari solver utama dan tersedia dalam dua level kedalaman."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {scenarioAnalysisLevels.map((item) => (
            <article key={item.title} className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-semibold text-ink">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
                {item.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
        <div className="rounded-[24px] border border-sky-200 bg-sky-50/80 p-5">
          <h3 className="text-base font-semibold text-sky-950">Apa yang dibaca user dari Scenario Analysis</h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-sky-950/80">
            {scenarioAnalysisOutputs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </GuideSection>
    </AppLayout>
  );
}
