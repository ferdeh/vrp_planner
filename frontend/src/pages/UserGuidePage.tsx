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
      "Periksa summary scenario, route grafik, depot operation, unserved order, dan compare antar scenario.",
  },
];

const objectives = [
  {
    title: "Minimize truck count",
    description: "Mengurangi jumlah truck aktif yang harus keluar depot.",
  },
  {
    title: "Minimize distance",
    description: "Mengurangi total km perjalanan seluruh truck.",
  },
  {
    title: "Minimize truck time",
    description: "Mengurangi total waktu perjalanan truck di jalan.",
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
    description: "Batas target kedatangan untuk order priority.",
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
    description: "Order priority wajib tiba sebelum atau sama dengan ETA yang diisi user.",
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
    description: "Shipment boleh tidak terlayani dengan penalty.",
  },
  {
    title: "Time window SPBU",
    description: "Truck boleh terlambat dari TW End SPBU, tetapi setiap menit terlambat kena penalty.",
  },
  {
    title: "SPBU Priority",
    description: "Truck boleh melewati ETA order priority, tetapi setiap menit terlambat kena penalty.",
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
];

const outputs = [
  "Summary scenario menunjukkan truck aktif, distance, time, cost, penalty, dan depot operation.",
  "Route Grafik memperlihatkan urutan pergerakan truck termasuk Depot Service dan Depot Reload.",
  "Route per MT menampilkan stop detail, ETA, ETD, volume kirim, dan trip per truck.",
  "Unserved order menampilkan order yang tidak terlayani beserta alasannya.",
  "Compare scenario memudahkan membandingkan hasil beberapa skenario pada hari yang sama.",
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
        description="Objective menentukan preferensi biaya solver. Anda dapat menyalakan lebih dari satu objective sekaligus."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          {objectives.map((item) => (
            <article key={item.title} className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-lg font-semibold text-ink">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">{item.description}</p>
            </article>
          ))}
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
      </GuideSection>
    </AppLayout>
  );
}
