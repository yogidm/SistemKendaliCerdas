"""
Media Pembelajaran Interaktif — Sistem Kendali Cerdas
=======================================================
Tab: Fuzzy | NN | GA | ANFIS | PSO | RL | Tugas | Kuis
Dependensi: pip install numpy matplotlib
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv, os, json
from datetime import datetime
from mpl_toolkits.mplot3d import Axes3D  # noqa
from matplotlib import colormaps
from matplotlib.patches import Circle


# ============================================================
#  UTILITY
# ============================================================
def export_csv(parent, columns, rows, default_name):
    path = filedialog.asksaveasfilename(
        parent=parent, defaultextension=".csv",
        initialfile=default_name, filetypes=[("CSV", "*.csv")])
    if not path:
        return
    try:
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(rows)
        messagebox.showinfo("Export Berhasil", f"Tersimpan:\n{path}")
    except Exception as e:
        messagebox.showerror("Export Gagal", str(e))


def simulate_pid_plant(Kp, Ki, Kd, T=6.0, dt=0.02, damping=2.0):
    steps = int(T / dt)
    x1 = x2 = 0.0
    e_int = 0.0
    e_prev = 0.0
    iae = 0.0
    ts, ys = [], []
    for i in range(steps):
        e = 1.0 - x1
        e_int += e * dt
        de = (e - e_prev) / dt
        u = float(np.clip(Kp * e + Ki * e_int + Kd * de, -10, 10))
        dx1 = x2
        dx2 = -damping * x2 - x1 + u
        x1 += dx1 * dt
        x2 += dx2 * dt
        iae += abs(e) * dt
        ts.append(i * dt)
        ys.append(x1)
        e_prev = e
    return np.array(ts), np.array(ys), iae


# ============================================================
#  TAB 1: FUZZY LOGIC
# ============================================================
class FuzzyTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        # --- Left panel ---
        left = ttk.LabelFrame(self, text="Parameter Studi Kasus", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Label(left, text="FUZZY — Kontrol Suhu Ruang",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=12, wrap=tk.WORD)
        info.pack(pady=4)
        info.insert(tk.END,
            "Rule base 3x3 (Mamdani) + defuzz centroid.\n"
            "Plant: dT/dt = k*(u/100)*40 - h*(T-Tamb) + dist\n\n"
            "Slider di bawah = 'studi kasus' nyata:\n"
            "  • Setpoint → operator mengubah target\n"
            "  • T_ambient → ruangan sekitar\n"
            "  • Disturbance → pintu dibuka / beban panas\n"
            "  • Sensor noise → ADC noisy di industri\n"
            "  • Cool rate → koefisien kehilangan panas")
        info.config(state=tk.DISABLED)

        self.sp_var = tk.DoubleVar(value=60)
        self.tamb_var = tk.DoubleVar(value=25)
        self.dist_var = tk.DoubleVar(value=0)
        self.noise_var = tk.DoubleVar(value=0)
        self.h_var = tk.DoubleVar(value=0.15)

        for label, var, lo, hi, fmt in [
            ("Setpoint (°C)", self.sp_var, 30, 90, "{:.1f}"),
            ("T_ambient (°C)", self.tamb_var, 10, 40, "{:.1f}"),
            ("Disturbance (heat/s)", self.dist_var, -5, 5, "{:.2f}"),
            ("Sensor noise σ (°C)", self.noise_var, 0, 3, "{:.2f}"),
            ("Cool rate h", self.h_var, 0.05, 0.4, "{:.2f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=18).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=180).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Start", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="T=-- °C  Daya=-- %", font=("Courier", 9))
        self.status.pack()
        self.gauge = ttk.Progressbar(left, length=260, maximum=100)
        self.gauge.pack(pady=4)
        self.gauge_lbl = ttk.Label(left, text="Heater 0%", font=("Courier", 9))
        self.gauge_lbl.pack()

        # --- Right panel ---
        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.reset()
        self.init_plot()

    # --- Fuzzy core ---
    @staticmethod
    def tri(x, a, b, c):
        y = np.zeros_like(x, dtype=float)
        if b > a:
            m = (x >= a) & (x < b); y[m] = (x[m] - a) / (b - a)
        if c > b:
            m = (x > b) & (x <= c); y[m] = (c - x[m]) / (c - b)
        y[x == b] = 1.0
        return y

    def fuzzify(self, e, de):
        eF = (self.tri(np.array([e]), -1.2, -1.0, -0.2)[0],
              self.tri(np.array([e]), -0.5, 0.0, 0.5)[0],
              self.tri(np.array([e]), 0.2, 1.0, 1.2)[0])
        dF = (self.tri(np.array([de]), -1.2, -1.0, -0.2)[0],
              self.tri(np.array([de]), -0.5, 0.0, 0.5)[0],
              self.tri(np.array([de]), 0.2, 1.0, 1.2)[0])
        return eF, dF

    def infer(self, e, de):
        eF, dF = self.fuzzify(e, de)
        eN, eZ, eP = eF; dN, dZ, dP = dF
        rules = [(eN,dN,-1.0),(eN,dZ,-1.0),(eN,dP,-0.5),
                 (eZ,dN,-1.0),(eZ,dZ,0.0),(eZ,dP,0.5),
                 (eP,dN,0.5),(eP,dZ,1.0),(eP,dP,1.0)]
        wsum = vsum = 0.0
        for we, wd, out in rules:
            w = min(we, wd); wsum += w; vsum += w * out
        return vsum / wsum if wsum > 1e-9 else 0.0

    # --- Simulation ---
    def reset(self):
        self.T = 25.0
        self.prev_e = 0.0
        self.t = 0.0
        self.t_hist, self.T_hist, self.u_hist, self.sp_hist = [], [], [], []
        self.running = False

    def init_plot(self):
        self.ax1.clear(); self.ax2.clear()
        self.ax1.set_xlim(0, 30); self.ax1.set_ylim(15, 100)
        self.ax1.set_xlabel("Waktu (s)"); self.ax1.set_ylabel("Suhu (°C)")
        self.ax1.grid(alpha=0.3)
        self.ax1.set_title("Respons Sistem Kontrol Suhu")
        self.line_T, = self.ax1.plot([], [], 'b-', lw=2, label='T aktual')
        self.line_sp, = self.ax1.plot([], [], 'r--', lw=1.4, label='Setpoint')
        self.ax1.legend(loc='lower right', fontsize=8)

        self.ax2.set_xlabel("Waktu (s)"); self.ax2.set_ylabel("Daya heater (%)")
        self.ax2.set_ylim(-2, 102); self.ax2.grid(alpha=0.3)
        self.ax2.set_title("Sinyal Kontrol (output fuzzy)")
        self.line_u, = self.ax2.plot([], [], 'g-', lw=1.5)
        self.canvas.draw()

    def step(self):
        sp = self.sp_var.get()
        Tamb = self.tamb_var.get()
        dist = self.dist_var.get()
        noise = self.noise_var.get()
        h = self.h_var.get()

        T_meas = self.T + (np.random.randn() * noise if noise > 0 else 0)
        e = float(np.clip((sp - T_meas) / 30.0, -1.2, 1.2))
        de = float(np.clip((e - self.prev_e) / 0.5, -1.2, 1.2))
        u_norm = self.infer(e, de)
        u = float(np.clip((u_norm + 1.0) * 50.0, 0, 100))

        dT = 0.8 * (u / 100.0) * 40.0 - h * (self.T - Tamb) + dist
        self.T += dT * 0.1
        self.prev_e = e
        self.t += 0.1

        self.t_hist.append(self.t); self.T_hist.append(self.T)
        self.u_hist.append(u); self.sp_hist.append(sp)
        if len(self.t_hist) > 400:
            for arr in (self.t_hist, self.T_hist, self.u_hist, self.sp_hist):
                del arr[0]

        self.line_T.set_data(self.t_hist, self.T_hist)
        self.line_sp.set_data(self.t_hist, self.sp_hist)
        self.line_u.set_data(self.t_hist, self.u_hist)
        self.ax1.set_xlim(max(0, self.t - 40), max(40, self.t))
        self.ax2.set_xlim(max(0, self.t - 40), max(40, self.t))
        self.canvas.draw_idle()

        self.status.config(text=f"T={self.T:5.1f}°C  Daya={u:5.1f}%  e={e:+.2f}")
        self.gauge['value'] = u
        self.gauge_lbl.config(text=f"Heater {u:.0f}%")

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Start")

    def loop(self):
        if not self.running: return
        self.step()
        self.after(100, self.loop)

    def export(self):
        rows = [(round(t,2), round(T,3), round(sp,2), round(u,2))
                for t, T, sp, u in zip(self.t_hist, self.T_hist,
                                       self.sp_hist, self.u_hist)]
        export_csv(self, ["t_s", "T_C", "setpoint_C", "heater_pct"], rows,
                   f"fuzzy_log_{datetime.now():%Y%m%d_%H%M}.csv")


# ============================================================
#  TAB 2: NEURAL NETWORK
# ============================================================
class NNTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter Studi Kasus", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="NN — MLP 1-H-1", font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=10, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "NN belajar pola dari data lewat backprop.\n"
            "Studi kasus: soft-sensor industri untuk\n"
            "mengaproksimasi fungsi nonlinier dari data noisy.\n\n"
            "Slider:\n"
            "  • Learning rate → laju belajar\n"
            "  • Hidden neuron → kapasitas model\n"
            "  • Noise σ → kualitas sensor\n"
            "  • N data → jumlah titik training")
        info.config(state=tk.DISABLED)

        self.lr_var = tk.DoubleVar(value=0.1)
        self.hidden_var = tk.IntVar(value=10)
        self.noise_var = tk.DoubleVar(value=0.05)
        self.n_var = tk.IntVar(value=80)

        for label, var, lo, hi, fmt in [
            ("Learning rate", self.lr_var, 0.001, 0.5, "{:.3f}"),
            ("Hidden neuron", self.hidden_var, 2, 30, "{:d}"),
            ("Noise σ", self.noise_var, 0.0, 0.3, "{:.2f}"),
            ("N data", self.n_var, 20, 300, "{:d}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=150).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Train", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Rebuild", command=self.rebuild).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Epoch: 0 | Loss: --", font=("Courier", 9))
        self.status.pack()
        self.loss_bar = ttk.Progressbar(left, length=260, maximum=100)
        self.loss_bar.pack(pady=4)
        self.loss_lbl = ttk.Label(left, text="MSE (relative)", font=("Courier", 9))
        self.loss_lbl.pack()

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.rebuild()

    def rebuild(self):
        rng = np.random.default_rng(0)
        n = self.n_var.get()
        self.X = np.linspace(-np.pi, np.pi, n).reshape(-1, 1)
        self.Y = np.sin(self.X) + self.noise_var.get() * rng.standard_normal((n, 1))
        H = self.hidden_var.get()
        self.W1 = rng.standard_normal((1, H)) * 0.5
        self.b1 = np.zeros((1, H))
        self.W2 = rng.standard_normal((H, 1)) * 0.5
        self.b2 = np.zeros((1, 1))
        self.epoch = 0
        self.losses = []
        self.draw()

    def forward(self, X):
        self.z1 = X @ self.W1 + self.b1
        self.a1 = np.tanh(self.z1)
        return self.a1 @ self.W2 + self.b2

    def train_step(self, n=20):
        lr = self.lr_var.get()
        for _ in range(n):
            Yhat = self.forward(self.X)
            err = Yhat - self.Y
            self.losses.append(float(np.mean(err ** 2)))
            dY = 2 * err / len(self.X)
            dW2 = self.a1.T @ dY
            db2 = dY.sum(axis=0, keepdims=True)
            da1 = dY @ self.W2.T
            dz1 = da1 * (1 - self.a1 ** 2)
            dW1 = self.X.T @ dz1
            db1 = dz1.sum(axis=0, keepdims=True)
            self.W2 -= lr * dW2; self.b2 -= lr * db2
            self.W1 -= lr * dW1; self.b1 -= lr * db1
            self.epoch += 1

    def draw(self):
        self.ax1.clear()
        Xf = np.linspace(-np.pi, np.pi, 200).reshape(-1, 1)
        Yf = self.forward(Xf)
        self.ax1.scatter(self.X, self.Y, s=14, c='b', alpha=0.6, label='Data (noisy)')
        self.ax1.plot(Xf, Yf, 'r-', lw=2, label='Prediksi NN')
        self.ax1.plot(Xf, np.sin(Xf), 'k--', lw=1, label='Ground truth')
        self.ax1.set_title(f"Approksimasi sin(x)  |  epoch={self.epoch}")
        self.ax1.grid(alpha=0.3); self.ax1.legend(loc='upper right', fontsize=8)

        self.ax2.clear()
        if self.losses:
            self.ax2.plot(self.losses, 'g-', lw=1.3)
            self.ax2.set_yscale('log')
            self.ax2.set_title(f"Kurva Loss (MSE={self.losses[-1]:.2e})")
        else:
            self.ax2.set_title("Kurva Loss")
        self.ax2.set_xlabel("Iterasi"); self.ax2.set_ylabel("MSE (log)")
        self.ax2.grid(alpha=0.3, which='both')
        self.canvas.draw_idle()

        if self.losses:
            mse = self.losses[-1]
            pct = float(np.clip(100 * (1 - min(1, mse / 0.5)), 0, 100))
            self.loss_bar['value'] = pct
            self.loss_lbl.config(text=f"MSE={mse:.3e}  ({pct:.0f}% good)")

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Train")

    def loop(self):
        if not self.running: return
        self.train_step(20)
        self.draw()
        self.status.config(text=f"Epoch: {self.epoch} | Loss: {self.losses[-1]:.3e}")
        if self.losses[-1] < 1e-6 or self.epoch > 8000:
            self.running = False; self.btn.config(text="▶ Train"); return
        self.after(50, self.loop)

    def export(self):
        Xf = np.linspace(-np.pi, np.pi, 300)
        Yf = self.forward(Xf.reshape(-1, 1)).ravel()
        rows = [(round(float(x), 4), round(float(y), 5)) for x, y in zip(Xf, Yf)]
        export_csv(self, ["x", "y_pred"], rows,
                   f"nn_prediction_{datetime.now():%Y%m%d_%H%M}.csv")

# ============================================================
#  TAB 2.1: NEURAL NETWORK FLOW
# ============================================================

class NNFlowTab(ttk.Frame):
    """Diagram MLP 1-6-1: bobot berwarna, neuron berdenyut saat inference."""
    def __init__(self, master):
        super().__init__(master, padding=8)
        left = ttk.LabelFrame(self, text="NN Neuron Flow", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="Neuron Flow Visualizer",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=15, wrap=tk.WORD, font=("Arial", 9))
        info.pack()
        info.insert(tk.END, """TEORI — Neuron & Bobot
Setiap neuron = unit komputasi: y = f(Σwᵢxᵢ + b).
Bobot w menyatakan 'kekuatan' koneksi antar neuron.

WARNA GARIS
  🔴 Merah  → bobot POSITIF (memperkuat sinyal)
  🔵 Biru   → bobot NEGATIF (menghambat sinyal)
  Ketebalan = |w| (besar → tebal)

UKURAN LINGKARAN
  Radius neuron ∝ |aktivasi|. Neuron yang
  'menyala' ukurannya membesar dan berdenyut
  (simbol pulsa sinyal).

CARA BACA
  1. Set input x → perhatikan node hidden mana
     yang menyala. Itulah 'representasi internal'
     jaringan terhadap x.
  2. Klik Train → bobot berubah warna/tebal
     sampai output ≈ sin(x).
  3. Setelah training, hidden neuron biasanya
     'mengkode' segmen-segmen berbeda dari sin(x).

APLIKASI INDUSTRI
  Soft-sensor (estimasi variabel sulit diukur),
  prediksi kualitas, kontroler NN adaptif,
  identifikasi plant nonlinier.""")
        info.config(state=tk.DISABLED)

        self.x_var = tk.DoubleVar(value=0.0)
        f = ttk.Frame(left); f.pack(fill=tk.X, pady=6)
        ttk.Label(f, text="Input x:", width=8).pack(side=tk.LEFT)
        ttk.Scale(f, from_=-3.14, to=3.14, variable=self.x_var,
                  orient=tk.HORIZONTAL, length=180).pack(side=tk.LEFT)
        self.x_lbl = ttk.Label(f, text="0.00", width=6, font=("Courier", 9))
        self.x_lbl.pack(side=tk.LEFT)
        self.x_var.trace_add("write",
            lambda *a: (self.x_lbl.config(text=f"{self.x_var.get():.2f}"), self.draw()))

        row = ttk.Frame(left); row.pack(pady=6)
        ttk.Button(row, text="▶ Train 300x", command=self.train).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)

        self.out_lbl = ttk.Label(left, text="y = --",
                                 font=("Courier", 12, "bold"), foreground="navy")
        self.out_lbl.pack(pady=6)
        self.epoch_lbl = ttk.Label(left, text="Epoch: 0", font=("Courier", 9))
        self.epoch_lbl.pack()

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(9, 6), dpi=80)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.H = 6
        self.epoch = 0
        self.phase = 0.0
        self.reset()
        self.animate()

    def reset(self):
        rng = np.random.default_rng(7)
        self.W1 = rng.standard_normal((1, self.H)) * 0.5
        self.b1 = np.zeros((1, self.H))
        self.W2 = rng.standard_normal((self.H, 1)) * 0.5
        self.b2 = np.zeros((1, 1))
        self.X = np.linspace(-np.pi, np.pi, 60).reshape(-1, 1)
        self.Y = np.sin(self.X)
        self.epoch = 0
        self.draw()

    def forward(self, x):
        z1 = x * self.W1 + self.b1
        a1 = np.tanh(z1)
        y = a1 @ self.W2 + self.b2
        return a1[0], float(y[0, 0])

    def train(self):
        lr = 0.1
        for _ in range(300):
            z1 = self.X @ self.W1 + self.b1
            a1 = np.tanh(z1)
            yh = a1 @ self.W2 + self.b2
            err = yh - self.Y
            dY = 2 * err / len(self.X)
            dW2 = a1.T @ dY
            db2 = dY.sum(axis=0, keepdims=True)
            da1 = dY @ self.W2.T
            dz1 = da1 * (1 - a1 ** 2)
            dW1 = self.X.T @ dz1
            db1 = dz1.sum(axis=0, keepdims=True)
            self.W2 -= lr * dW2; self.b2 -= lr * db2
            self.W1 -= lr * dW1; self.b1 -= lr * db1
            self.epoch += 1
        self.draw()

    def draw(self):
        self.ax.clear()
        self.ax.set_xlim(-0.35, 2.35); self.ax.set_ylim(-0.25, 1.25)
        self.ax.axis('off')

        x = self.x_var.get()
        a1, y = self.forward(x)

        p_in = (0.0, 0.5)
        p_hid = [(1.0, 0.1 + i * 0.8 / (self.H - 1)) for i in range(self.H)]
        p_out = (2.0, 0.5)

        # Edges in→hidden
        for i, p in enumerate(p_hid):
            self._edge(p_in, p, self.W1[0, i])
        # Edges hidden→out
        for i, p in enumerate(p_hid):
            self._edge(p, p_out, self.W2[i, 0])

        # Nodes
        self._node(p_in, abs(np.tanh(x)), '#2e86c1', f'x\n{x:+.2f}')
        for i, p in enumerate(p_hid):
            col = '#27ae60' if a1[i] > 0 else '#c0392b'
            self._node(p, abs(a1[i]), col, f'h{i+1}\n{a1[i]:+.2f}')
        self._node(p_out, abs(np.tanh(y)), '#8e44ad', f'y\n{y:+.2f}')

        self.ax.text(0.0, 1.18, "INPUT", ha='center', fontsize=10, fontweight='bold')
        self.ax.text(1.0, 1.18, "HIDDEN (tanh)", ha='center', fontsize=10, fontweight='bold')
        self.ax.text(2.0, 1.18, "OUTPUT", ha='center', fontsize=10, fontweight='bold')
        self.ax.text(0.5, -0.18, f"Target = sin(x) = {np.sin(x):+.4f}",
                     fontsize=10, color='gray')

        # Legend
        self.ax.plot([], [], color='#c0392b', lw=2.5, label='w > 0 (excitatory)')
        self.ax.plot([], [], color='#2980b9', lw=2.5, label='w < 0 (inhibitory)')
        self.ax.legend(loc='lower left', fontsize=8, framealpha=0.9)

        self.canvas.draw_idle()
        self.out_lbl.config(
            text=f"y_pred = {y:+.4f}   |   target = {np.sin(x):+.4f}")
        self.epoch_lbl.config(text=f"Epoch: {self.epoch}")

    def _node(self, pos, act, color, label):
        pulse = 1.0 + 0.18 * np.sin(self.phase)
        r = 0.045 + 0.055 * act * pulse
        self.ax.add_patch(Circle(pos, r, color=color, alpha=0.75, zorder=5))
        self.ax.text(pos[0], pos[1], label, ha='center', va='center',
                     fontsize=7, zorder=6,
                     color='white' if act > 0.35 else 'black')

    def _edge(self, p1, p2, w):
        color = '#c0392b' if w > 0 else '#2980b9'
        lw = 0.5 + min(abs(w) * 3.5, 5.5)
        alpha = min(0.25 + abs(w) * 0.55, 0.95)
        self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]],
                     color=color, lw=lw, alpha=alpha, zorder=1)

    def animate(self):
        self.phase += 0.35
        self.draw()
        self.after(90, self.animate)

# ============================================================
#  TAB 3: GENETIC ALGORITHM
# ============================================================
class GATab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter Studi Kasus", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="GA — Auto-tuning PID", font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=9, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "GA evolusi populasi PID untuk plant orde-2.\n"
            "G(s) = 1/(s² + d·s + 1). Fitness = 1/(1+IAE).\n\n"
            "Studi kasus: auto-tune di PLC saat plant\n"
            "berubah (damping naik karena keausan).")
        info.config(state=tk.DISABLED)

        self.pop_var = tk.IntVar(value=30)
        self.mut_var = tk.DoubleVar(value=0.3)
        self.damp_var = tk.DoubleVar(value=2.0)

        for label, var, lo, hi, fmt in [
            ("Populasi", self.pop_var, 10, 80, "{:d}"),
            ("Mutation rate", self.mut_var, 0.0, 1.0, "{:.2f}"),
            ("Plant damping d", self.damp_var, 0.5, 4.0, "{:.2f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=16).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=150).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Evolve", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Gen: 0 | Best fit: --", font=("Courier", 9))
        self.status.pack()
        self.best_lbl = ttk.Label(left, text="Kp=-- Ki=-- Kd=--", font=("Courier", 9))
        self.best_lbl.pack()
        self.iae_lbl = ttk.Label(left, text="IAE: --", font=("Courier", 9))
        self.iae_lbl.pack()
        self.fit_bar = ttk.Progressbar(left, length=260, maximum=100)
        self.fit_bar.pack(pady=4)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.reset()

    def reset(self):
        n = self.pop_var.get()
        self.pop = np.random.uniform([0, 0, 0], [10, 5, 5], (n, 3))
        self.gen = 0
        self.best_fit_hist = []
        self.iae_hist = []
        self.eval_pop()
        self.draw()

    def eval_pop(self):
        d = self.damp_var.get()
        fits = np.empty(len(self.pop))
        iaes = np.empty(len(self.pop))
        for i, ind in enumerate(self.pop):
            _, _, iae = simulate_pid_plant(*ind, damping=d)
            iaes[i] = iae
            fits[i] = 1.0 / (1.0 + iae)
        self.fits = fits; self.iaes = iaes
        self.best_idx = int(np.argmax(fits))

    def evolve(self):
        n = len(self.pop)
        new = [self.pop[self.best_idx].copy()]
        while len(new) < n:
            i1, i2 = np.random.choice(n, 2, replace=False)
            p1 = self.pop[i1] if self.fits[i1] > self.fits[i2] else self.pop[i2]
            i3, i4 = np.random.choice(n, 2, replace=False)
            p2 = self.pop[i3] if self.fits[i3] > self.fits[i4] else self.pop[i4]
            a = np.random.rand(3)
            child = a * p1 + (1 - a) * p2
            if np.random.rand() < self.mut_var.get():
                child += np.random.randn(3) * np.array([0.5, 0.2, 0.2])
            new.append(np.clip(child, [0, 0, 0], [10, 5, 5]))
        self.pop = np.array(new)
        self.gen += 1
        self.eval_pop()
        self.best_fit_hist.append(float(self.fits[self.best_idx]))
        self.iae_hist.append(float(self.iaes[self.best_idx]))

    def draw(self):
        best = self.pop[self.best_idx]
        t, y, iae = simulate_pid_plant(*best, damping=self.damp_var.get())

        self.ax1.clear()
        self.ax1.plot(t, y, 'b-', lw=2, label='y(t)')
        self.ax1.axhline(1.0, color='r', ls='--', lw=1.2, label='Setpoint')
        self.ax1.set_ylim(-0.2, 1.6)
        self.ax1.set_xlabel("Waktu (s)"); self.ax1.set_ylabel("Output")
        self.ax1.set_title(f"Respons Step — PID Terbaik (Gen {self.gen})")
        self.ax1.grid(alpha=0.3); self.ax1.legend(fontsize=8)

        self.ax2.clear()
        if self.best_fit_hist:
            self.ax2.plot(self.best_fit_hist, 'g-o', lw=1.6, ms=4, label='Best fitness')
            self.ax2.set_xlabel("Generasi"); self.ax2.set_ylabel("Fitness")
        else:
            self.ax2.set_title("Kurva Konvergensi GA")
            self.ax2.set_xlabel("Generasi"); self.ax2.set_ylabel("Fitness")
        self.ax2.set_title("Kurva Konvergensi GA")
        self.ax2.grid(alpha=0.3)
        self.canvas.draw_idle()

        self.best_lbl.config(text=f"Kp={best[0]:.3f}  Ki={best[1]:.3f}  Kd={best[2]:.3f}")
        self.iae_lbl.config(text=f"IAE = {iae:.4f}")
        if self.best_fit_hist:
            self.fit_bar['value'] = float(np.clip(self.fits[self.best_idx] * 100, 0, 100))

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Evolve")

    def loop(self):
        if not self.running: return
        for _ in range(3):
            self.evolve()
        self.draw()
        self.status.config(text=f"Gen: {self.gen} | Best fit: {self.fits[self.best_idx]:.4f}")
        if self.gen > 100:
            self.running = False; self.btn.config(text="▶ Evolve"); return
        self.after(50, self.loop)

    def export(self):
        rows = [(g + 1, round(f, 5), round(i, 5))
                for g, (f, i) in enumerate(zip(self.best_fit_hist, self.iae_hist))]
        export_csv(self, ["generasi", "best_fitness", "IAE"], rows,
                   f"ga_log_{datetime.now():%Y%m%d_%H%M}.csv")


# ============================================================
#  TAB 3: GENETIC ALGORITHM POPULATION LANDSCAPE
# ============================================================

class GALandscapeTab(ttk.Frame):
    """Visualisasi populasi GA di landscape fitness 2D (Kp, Ki)."""
    def __init__(self, master):
        super().__init__(master, padding=8)
        left = ttk.LabelFrame(self, text="GA Population Landscape", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="GA Landscape Visualizer",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=15, wrap=tk.WORD, font=("Arial", 9))
        info.pack()
        info.insert(tk.END, """TEORI — GA sebagai Pencarian di Landscape
Bayangkan 'ruang solusi' sebagai medan pegunungan.
Setiap titik (Kp, Ki) punya nilai fitness = ketinggian.
Puncak tertinggi = PID terbaik.

ELEMEN VISUAL
  • Warna latar (contour) = nilai fitness untuk
    SEMUA kombinasi (Kp,Ki) yang mungkin
  • Titik = satu individu dalam populasi
    - terang  → fitness tinggi (baik)
    - gelap   → fitness rendah
  • ⭐ Emas  = individu terbaik (gbest)
  • Garis oranye = PROSES CROSSOVER
    (dari 2 parent → anak)
  • ✗ merah = anak tanpa mutasi
  • ✗ ungu  = anak yang di-MUTASI

CARA BACA EVOLUSI
  Gen 0:  populasi tersebar acak di lembah
  Gen 10: titik mulai mendaki
  Gen 30: populasi mengerumun di puncak
  Gen 50: konvergen (semua titik di puncak)

APLIKASI INDUSTRI
  Auto-tuning PID, optimasi resep proses,
  desain filter, penjadwalan produksi.""")
        info.config(state=tk.DISABLED)

        self.pop_var = tk.IntVar(value=30)
        self.mut_var = tk.DoubleVar(value=0.3)
        self.damp_var = tk.DoubleVar(value=2.0)
        self.show_contour = tk.BooleanVar(value=True)

        for label, var, lo, hi, fmt in [
            ("Populasi", self.pop_var, 10, 60, "{:d}"),
            ("Mutation rate", self.mut_var, 0.0, 1.0, "{:.2f}"),
            ("Plant damping", self.damp_var, 0.5, 4.0, "{:.2f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=140).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        ttk.Checkbutton(left, text="Tampilkan contour fitness",
                        variable=self.show_contour).pack(anchor='w', pady=2)

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Evolve", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Gen: 0 | Best fit: --",
                                font=("Courier", 9))
        self.status.pack()
        self.best_lbl = ttk.Label(left, text="Kp=-- Ki=--",
                                  font=("Courier", 9), foreground="navy")
        self.best_lbl.pack()
        self.fit_bar = ttk.Progressbar(left, length=250, maximum=100)
        self.fit_bar.pack(pady=4)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(9, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(121)
        self.ax2 = self.fig.add_subplot(122)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._cache = None; self._cache_d = None
        self.reset()

    def fitness_2d(self, Kp, Ki, Kd=3.0, d=None):
        if d is None: d = self.damp_var.get()
        _, _, iae = simulate_pid_plant(Kp, Ki, Kd, damping=d)
        return 1.0 / (1.0 + iae)

    def reset(self):
        n = self.pop_var.get()
        rng = np.random.default_rng()
        self.pop = np.column_stack([rng.uniform(0, 10, n),
                                    rng.uniform(0, 5, n)])
        self.fits = np.array([self.fitness_2d(*p) for p in self.pop])
        self.gen = 0
        self.fit_hist = [float(self.fits.max())]
        self.crossover_events = []
        self.draw()

    def evolve(self):
        n = len(self.pop)
        new_pop = [self.pop[int(np.argmax(self.fits))].copy()]  # elitism
        while len(new_pop) < n:
            i1, i2 = np.random.choice(n, 2, replace=False)
            p1 = self.pop[i1] if self.fits[i1] > self.fits[i2] else self.pop[i2]
            i3, i4 = np.random.choice(n, 2, replace=False)
            p2 = self.pop[i3] if self.fits[i3] > self.fits[i4] else self.pop[i4]
            a = np.random.rand(2)
            child = a * p1 + (1 - a) * p2
            mutated = False
            if np.random.rand() < self.mut_var.get():
                child += np.random.randn(2) * np.array([0.8, 0.4])
                mutated = True
            child = np.clip(child, [0, 0], [10, 5])
            new_pop.append(child)
            self.crossover_events.append({'p1': p1.copy(), 'p2': p2.copy(),
                                          'child': child.copy(),
                                          'age': 0, 'mut': mutated})
        self.pop = np.array(new_pop)
        self.fits = np.array([self.fitness_2d(*p) for p in self.pop])
        self.gen += 1
        self.fit_hist.append(float(self.fits.max()))
        for ev in self.crossover_events: ev['age'] += 1
        self.crossover_events = [ev for ev in self.crossover_events if ev['age'] < 4]

    def draw(self):
        d = self.damp_var.get()
        if self._cache is None or self._cache_d != d:
            Ng = 25
            Kps = np.linspace(0, 10, Ng)
            Kis = np.linspace(0, 5, Ng)
            Z = np.zeros((Ng, Ng))
            for i, kp in enumerate(Kps):
                for j, ki in enumerate(Kis):
                    Z[j, i] = self.fitness_2d(kp, ki, 3.0, d)
            self._cache = (Kps, Kis, Z); self._cache_d = d
        Kps, Kis, Z = self._cache

        self.ax1.clear()
        if self.show_contour.get():
            self.ax1.contourf(Kps, Kis, Z, levels=15, cmap='YlGnBu', alpha=0.75)
            self.ax1.contour(Kps, Kis, Z, levels=15,
                             colors='white', linewidths=0.4, alpha=0.6)

        cmin, cmax = self.fits.min(), self.fits.max()
        rng = max(cmax - cmin, 1e-9)
        norm = (self.fits - cmin) / rng
        self.ax1.scatter(self.pop[:, 0], self.pop[:, 1], c=norm, cmap='autumn',
                         s=70, edgecolors='k', linewidths=0.5, zorder=5)

        # crossover animation
        for ev in self.crossover_events:
            alpha = 0.9 * (1 - ev['age'] / 4)
            self.ax1.plot([ev['p1'][0], ev['p2'][0]], [ev['p1'][1], ev['p2'][1]],
                          color='orange', lw=1.3, alpha=alpha, zorder=3)
            self.ax1.plot([ev['child'][0]], [ev['child'][1]],
                          marker='x', color='purple' if ev['mut'] else 'red',
                          s=70, alpha=alpha, zorder=6)

        bi = int(np.argmax(self.fits))
        self.ax1.scatter([self.pop[bi, 0]], [self.pop[bi, 1]], marker='*',
                         s=320, c='gold', edgecolors='red', linewidths=1.7, zorder=10)

        self.ax1.set_xlim(-0.5, 10.5); self.ax1.set_ylim(-0.3, 5.3)
        self.ax1.set_xlabel("Kp"); self.ax1.set_ylabel("Ki")
        self.ax1.set_title(f"Populasi GA — Gen {self.gen}")
        self.ax1.grid(alpha=0.3)

        self.ax2.clear()
        self.ax2.plot(self.fit_hist, 'g-o', lw=1.7, ms=4)
        self.ax2.set_xlabel("Generasi"); self.ax2.set_ylabel("Best fitness")
        self.ax2.set_title("Konvergensi GA")
        self.ax2.grid(alpha=0.3)
        self.canvas.draw_idle()

        best = self.pop[bi]
        self.best_lbl.config(text=f"Kp={best[0]:.2f}  Ki={best[1]:.2f}")
        self.fit_bar['value'] = float(np.clip(self.fits[bi] * 100, 0, 100))

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Evolve")

    def loop(self):
        if not self.running: return
        self.evolve(); self.draw()
        self.status.config(text=f"Gen: {self.gen} | Best fit: {self.fits.max():.4f}")
        if self.gen > 120:
            self.running = False; self.btn.config(text="▶ Evolve"); return
        self.after(300, self.loop)


# ============================================================
#  TAB 4: ANFIS
# ============================================================
class ANFIS:
    def __init__(self, n_mf=5, x_range=(-np.pi, np.pi)):
        self.n = n_mf
        self.c = np.linspace(x_range[0], x_range[1], n_mf)
        self.sigma = np.ones(n_mf) * (x_range[1] - x_range[0]) / n_mf
        rng = np.random.default_rng(1)
        self.a = rng.standard_normal(n_mf) * 0.1
        self.b = rng.standard_normal(n_mf) * 0.1
        self._cache = None

    def forward(self, X):
        X = X.ravel()
        mu = np.exp(-((X[:, None] - self.c[None, :]) ** 2) /
                    (2 * self.sigma[None, :] ** 2))
        S = mu.sum(axis=1, keepdims=True) + 1e-9
        wbar = mu / S
        g = self.a[None, :] * X[:, None] + self.b[None, :]
        y = (wbar * g).sum(axis=1)
        self._cache = (X, mu, S, wbar, g, y)
        return y

    def backward(self, Y, lr):
        X, mu, S, wbar, g, y = self._cache
        err = y - Y
        dL_dy = 2 * err

        dL_da = (dL_dy[:, None] * wbar * X[:, None]).sum(axis=0)
        dL_db = (dL_dy[:, None] * wbar).sum(axis=0)

        dL_dw = dL_dy[:, None] * (g - y[:, None]) / S
        dc = (dL_dw * mu * (X[:, None] - self.c[None, :]) /
              self.sigma[None, :] ** 2).sum(axis=0)
        ds = (dL_dw * mu * (X[:, None] - self.c[None, :]) ** 2 /
              self.sigma[None, :] ** 3).sum(axis=0)

        self.a -= lr * dL_da
        self.b -= lr * dL_db
        self.c -= lr * dc * 0.1
        self.sigma -= lr * ds * 0.1
        self.sigma = np.clip(self.sigma, 0.05, None)


class ANFISTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="ANFIS = Fuzzy + NN", font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=11, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "ANFIS = Adaptive Neuro-Fuzzy Inference System.\n"
            "Struktur fuzzy (MF Gaussian + rule Sugeno) yang\n"
            "PARAMETERNYA dilatih dengan gradient descent\n"
            "seperti layaknya Neural Network.\n\n"
            "Studi kasus: identifikasi plant nonlinier saat\n"
            "MF awal (premis) di-set asal-asalan — ANFIS\n"
            "BELAJAR menggeser c, σ, a, b sehingga output\n"
            "mendekati target.\n\n"
            "Bandingkan dengan tab NN: ANFIS lebih\n"
            "interpretable karena MF-nya bisa dibaca.")
        info.config(state=tk.DISABLED)

        self.nmf_var = tk.IntVar(value=5)
        self.lr_var = tk.DoubleVar(value=0.05)

        for label, var, lo, hi, fmt in [
            ("Jumlah MF", self.nmf_var, 3, 9, "{:d}"),
            ("Learning rate", self.lr_var, 0.001, 0.3, "{:.3f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=150).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Train", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Epoch: 0 | MSE: --", font=("Courier", 9))
        self.status.pack()
        self.loss_bar = ttk.Progressbar(left, length=260, maximum=100)
        self.loss_bar.pack(pady=4)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.reset()

    def reset(self):
        self.X = np.linspace(-np.pi, np.pi, 100)
        # target: kombinasi sin
        self.Y = 0.6 * np.sin(self.X) + 0.3 * np.sin(3 * self.X)
        self.anfis = ANFIS(self.nmf_var.get())
        self.epoch = 0
        self.losses = []
        self.draw()

    def train_step(self, n=10):
        lr = self.lr_var.get()
        for _ in range(n):
            Yh = self.anfis.forward(self.X)
            mse = float(np.mean((Yh - self.Y) ** 2))
            self.losses.append(mse)
            self.anfis.backward(self.Y, lr)
            self.epoch += 1

    def draw(self):
        self.ax1.clear()
        Yh = self.anfis.forward(self.X)
        self.ax1.plot(self.X, self.Y, 'k--', lw=1.4, label='Target')
        self.ax1.plot(self.X, Yh, 'r-', lw=2, label='Output ANFIS')
        self.ax1.set_title(f"ANFIS fitting  (epoch={self.epoch})")
        self.ax1.grid(alpha=0.3); self.ax1.legend(fontsize=8)

        self.ax2.clear()
        xg = np.linspace(-np.pi, np.pi, 200)
        for i in range(self.anfis.n):
            mu = np.exp(-((xg - self.anfis.c[i]) ** 2) / (2 * self.anfis.sigma[i] ** 2))
            self.ax2.plot(xg, mu, lw=1.3, label=f'MF{i+1}')
        self.ax2.set_title("Membership Function (setelah dilatih)")
        self.ax2.grid(alpha=0.3); self.ax2.legend(fontsize=7, ncol=3, loc='upper right')
        self.canvas.draw_idle()

        if self.losses:
            mse = self.losses[-1]
            self.loss_bar['value'] = float(np.clip(100 * (1 - min(1, mse / 0.5)), 0, 100))

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Train")

    def loop(self):
        if not self.running: return
        self.train_step(10)
        self.draw()
        self.status.config(text=f"Epoch: {self.epoch} | MSE: {self.losses[-1]:.3e}")
        if self.epoch > 4000: self.running = False; self.btn.config(text="▶ Train"); return
        self.after(50, self.loop)

    def export(self):
        Yh = self.anfis.forward(self.X)
        rows = [(round(float(x), 4), round(float(y), 4), round(float(p), 4))
                for x, y, p in zip(self.X, self.Y, Yh)]
        export_csv(self, ["x", "target", "anfis_output"], rows,
                   f"anfis_{datetime.now():%Y%m%d_%H%M}.csv")

# ============================================================
#  TAB 4.1: FUZZY RULE HEATMAP
# ============================================================


class FuzzyHeatmapTab(ttk.Frame):
    """Visualisasi 9 rule fuzzy 3x3 — sel menyala sesuai e/Δe."""
    def __init__(self, master):
        super().__init__(master, padding=8)
        left = ttk.LabelFrame(self, text="Fuzzy Rule Activation", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="Fuzzy Rule Heatmap",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=15, wrap=tk.WORD, font=("Arial", 9))
        info.pack()
        info.insert(tk.END, """TEORI — Rule Base sebagai Otak Fuzzy
Rule base fuzzy adalah kumpulan aturan IF-THEN:

  IF e IS PB AND Δe IS NB THEN u IS PS

Grid 3x3 = 9 kombinasi (e∈{NB,Z,PB}, Δe∈{NB,Z,PB}).
Contoh makna:
  • (Z, Z)   → error 0 & stabil  → u = 0 (diam)
  • (PB, Z)  → error besar (+)   → u = PB (panaskan)
  • (NB, PB) → error (-) membaik → u = NS (kurangi)

WARNA = 'kekuatan' rule = μ_min(e, Δe) = min(μ_e, μ_Δe)
  Terang/panas = rule sangat aktif
  Gelap        = rule tidak relevan
  Angka di sel = bobot aktivasi (0..1)

OUTPUT AKHIR = rata-rata terbobot:
        Σ (wᵢ × uᵢ) / Σ wᵢ
Inilah mengapa fuzzy HALUS — tidak ada 'saklar' tiba-
tiba. Beberapa rule selalu aktif bersamaan dengan
bobot berbeda.

CARA PAKAI
  • Geser slider e & Δe → lihat rule mana yang
    menyala. Perhatikan selalu ada 2-4 rule aktif.
  • Klik Random → coba berbagai kondisi
  • Klik e=0, Δe=0 → lihat state 'steady'""")
        info.config(state=tk.DISABLED)

        # Rules definition DULU sebelum slider
        self.rules = [
            ('NB','NB','NB', -1.0), ('NB','Z','NB', -1.0), ('NB','PB','NS', -0.5),
            ('Z','NB','NB', -1.0),  ('Z','Z','Z',    0.0), ('Z','PB','PS', +0.5),
            ('PB','NB','PS', +0.5), ('PB','Z','PB', +1.0), ('PB','PB','PB', +1.0),
        ]

        self.e_var = tk.DoubleVar(value=0.3)
        self.de_var = tk.DoubleVar(value=-0.2)

        for label, var, lo, hi in [("e", self.e_var, -1.2, 1.2),
                                    ("Δe", self.de_var, -1.2, 1.2)]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=5).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var,
                      orient=tk.HORIZONTAL, length=180).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=f"{var.get():+.2f}", width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl: (l.config(text=f"{v.get():+.2f}"), self.draw()))

        self.out_lbl = ttk.Label(left, text="u = --",
                                 font=("Courier", 12, "bold"), foreground="navy")
        self.out_lbl.pack(pady=6)
        self.out_bar = ttk.Progressbar(left, length=250, maximum=100)
        self.out_bar.pack()

        row = ttk.Frame(left); row.pack(pady=6)
        ttk.Button(row, text="🎲 Random",
                   command=lambda: (self.e_var.set(np.random.uniform(-1.2,1.2)),
                                    self.de_var.set(np.random.uniform(-1.2,1.2)))
                   ).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="🎯 e=0, Δe=0",
                   command=lambda: (self.e_var.set(0), self.de_var.set(0))
                   ).pack(side=tk.LEFT, padx=2)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(9, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(121)
        self.ax2 = self.fig.add_subplot(122)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.draw()

    def tri(self, x, a, b, c):
        y = 0.0
        if a <= x < b: y = (x - a) / (b - a) if b > a else 0
        elif b < x <= c: y = (c - x) / (c - b) if c > b else 0
        elif abs(x - b) < 1e-9: y = 1.0
        return float(np.clip(y, 0, 1))

    def mfs(self, x):
        return (self.tri(x, -1.2, -1.0, -0.2),
                self.tri(x, -0.5, 0.0, 0.5),
                self.tri(x, 0.2, 1.0, 1.2))

    def draw(self):
        e = self.e_var.get(); de = self.de_var.get()
        eF = self.mfs(e); dF = self.mfs(de)

        W = np.zeros((3, 3))
        for i in range(3):
            for j in range(3):
                W[i, j] = min(eF[i], dF[j])

        wsum = vsum = 0.0
        for i in range(3):
            for j in range(3):
                w = W[i, j]; out = self.rules[i*3 + j][3]
                wsum += w; vsum += w * out
        u_norm = vsum / wsum if wsum > 1e-9 else 0.0
        u = (u_norm + 1.0) * 50.0

        # Heatmap
        self.ax1.clear()
        self.ax1.imshow(W, cmap='hot', vmin=0, vmax=1, aspect='equal')
        for i in range(3):
            for j in range(3):
                w = W[i, j]
                txt = f"{self.rules[i*3+j][2]}\n{w:.2f}"
                col = 'white' if w > 0.5 else 'black'
                self.ax1.text(j, i, txt, ha='center', va='center',
                              fontsize=11, color=col, fontweight='bold')
        self.ax1.set_xticks([0,1,2]); self.ax1.set_xticklabels(['NB','Z','PB'])
        self.ax1.set_yticks([0,1,2]); self.ax1.set_yticklabels(['NB','Z','PB'])
        self.ax1.set_xlabel("Δe"); self.ax1.set_ylabel("e")
        self.ax1.set_title(f"Rule Activation  (e={e:+.2f}, Δe={de:+.2f})")

        # MF plot
        self.ax2.clear()
        xg = np.linspace(-1.2, 1.2, 200)
        for lbl_, col, mf in [
            ('NB', 'b', [self.tri(x,-1.2,-1.0,-0.2) for x in xg]),
            ('Z',  'g', [self.tri(x,-0.5,0.0,0.5) for x in xg]),
            ('PB', 'r', [self.tri(x,0.2,1.0,1.2) for x in xg]),
        ]:
            self.ax2.plot(xg, mf, color=col, lw=1.7, label=lbl_)
        self.ax2.axvline(e, color='k', ls=':', lw=1.2)
        for val, col in zip(eF, ['b', 'g', 'r']):
            if val > 0.01:
                self.ax2.plot([e], [val], 'o', color=col, ms=11,
                              markeredgecolor='k')
        self.ax2.set_ylim(0, 1.18); self.ax2.set_xlabel("e"); self.ax2.set_ylabel("μ")
        self.ax2.set_title(f"Membership  (μ = {eF[0]:.2f}, {eF[1]:.2f}, {eF[2]:.2f})")
        self.ax2.grid(alpha=0.3); self.ax2.legend(loc='upper right', fontsize=9)

        self.canvas.draw_idle()
        self.out_lbl.config(text=f"u = {u:5.1f}%  (u_norm={u_norm:+.3f})")
        self.out_bar['value'] = u

# ============================================================
#  TAB 4.2: ANFIS MF EVOLUTION
# ============================================================

class ANFISEvolutionTab(ttk.Frame):
    """MF Gaussian bergeser & melebar saat ANFIS training."""
    def __init__(self, master):
        super().__init__(master, padding=8)
        left = ttk.LabelFrame(self, text="ANFIS MF Evolution", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="MF Evolution Animation",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=15, wrap=tk.WORD, font=("Arial", 9))
        info.pack()
        info.insert(tk.END, """TEORI — ANFIS Belajar 'Bentuk' Fuzzy
ANFIS = Adaptive Neuro-Fuzzy Inference System.
Struktur: fuzzy Sugeno + algoritma gradient descent.

PARAMETER YANG DILATIH
  • c (center) → posisi MF di sumbu x
  • σ (sigma)  → lebar MF (seberapa 'longgar')
  • a, b       → koefisien output Sugeno (y = a·x + b)

AWAL: MF diletakkan rata (tidak tahu data).
SELAMA TRAINING: gradient descent menggeser c,
memperlebar/menyempitkan σ agar output fit
ke target  y = 0.6·sin(x) + 0.3·sin(3x).

VISUAL
  • MF solid (warna) = posisi SAAT INI
  • MF abu-abu transparan = JEJAK posisi lama
  • Perhatikan MF bagian tepi cenderung menyempit
    dan yang di tengah bergeser mengikuti 'bentuk'
    data

MENGAPA PENTING
Ini contoh pembelajaran END-TO-END: parameter
fuzzy bukan di-set manual oleh pakar, tapi
DIPELAJARI dari data. Cocok ketika pakar tidak
tahu MF ideal, tapi punya data historis.

APLIKASI
  Identifikasi plant nonlinier, prediksi deret
  waktu, kontrol adaptif, diagnostik industri.""")
        info.config(state=tk.DISABLED)

        self.nmf_var = tk.IntVar(value=5)
        self.lr_var = tk.DoubleVar(value=0.05)
        self.trail_alpha = tk.DoubleVar(value=0.25)

        for label, var, lo, hi, fmt in [
            ("Jumlah MF", self.nmf_var, 3, 8, "{:d}"),
            ("Learning rate", self.lr_var, 0.001, 0.2, "{:.3f}"),
            ("Trail alpha", self.trail_alpha, 0.05, 0.6, "{:.2f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=140).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Train", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Epoch: 0 | MSE: --",
                                font=("Courier", 9))
        self.status.pack()
        self.loss_bar = ttk.Progressbar(left, length=250, maximum=100)
        self.loss_bar.pack(pady=4)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(9, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.reset()

    def reset(self):
        n = self.nmf_var.get()
        self.X = np.linspace(-np.pi, np.pi, 80)
        self.Y = 0.6 * np.sin(self.X) + 0.3 * np.sin(3 * self.X)
        self.c = np.linspace(-np.pi, np.pi, n)
        self.sigma = np.ones(n) * 0.4
        rng = np.random.default_rng(1)
        self.a = rng.standard_normal(n) * 0.1
        self.b = rng.standard_normal(n) * 0.1
        self.epoch = 0
        self.losses = []
        self.history = []
        self.draw()

    def forward(self, X):
        X = np.asarray(X).ravel()
        mu = np.exp(-((X[:, None] - self.c[None, :])**2) /
                    (2 * self.sigma[None, :]**2 + 1e-9))
        S = mu.sum(axis=1, keepdims=True) + 1e-9
        wbar = mu / S
        g = self.a[None, :] * X[:, None] + self.b[None, :]
        y = (wbar * g).sum(axis=1)
        return mu, S, wbar, g, y

    def train_step(self, n_iter=1):
        lr = self.lr_var.get()
        for _ in range(n_iter):
            mu, S, wbar, g, y = self.forward(self.X)
            err = y - self.Y
            self.losses.append(float(np.mean(err ** 2)))
            dL_dy = 2 * err
            dL_da = (dL_dy[:, None] * wbar * self.X[:, None]).sum(axis=0)
            dL_db = (dL_dy[:, None] * wbar).sum(axis=0)
            dL_dw = dL_dy[:, None] * (g - y[:, None]) / S
            dc = (dL_dw * mu * (self.X[:, None] - self.c[None, :]) /
                  (self.sigma[None, :]**2 + 1e-9)).sum(axis=0)
            ds = (dL_dw * mu * (self.X[:, None] - self.c[None, :])**2 /
                  (self.sigma[None, :]**3 + 1e-9)).sum(axis=0)
            self.a -= lr * dL_da
            self.b -= lr * dL_db
            self.c -= lr * dc * 0.1
            self.sigma -= lr * ds * 0.1
            self.sigma = np.clip(self.sigma, 0.05, 3.0)
            self.epoch += 1
            if self.epoch % 5 == 0:
                self.history.append((self.c.copy(), self.sigma.copy()))
                if len(self.history) > 60: self.history.pop(0)

    def draw(self):
        Yh = self.forward(self.X)[-1]

        self.ax1.clear()
        self.ax1.plot(self.X, self.Y, 'k--', lw=1.5, label='Target')
        self.ax1.plot(self.X, Yh, 'r-', lw=2, label='ANFIS')
        self.ax1.set_title(f"Fitting  |  epoch = {self.epoch}")
        self.ax1.grid(alpha=0.3); self.ax1.legend(fontsize=9)

        self.ax2.clear()
        xg = np.linspace(-np.pi, np.pi, 200)
        alpha_max = self.trail_alpha.get()
        # trails
        for k, (c_old, s_old) in enumerate(self.history):
            a = alpha_max * (k + 1) / max(len(self.history), 1)
            for i in range(len(c_old)):
                mu = np.exp(-((xg - c_old[i])**2) / (2 * s_old[i]**2 + 1e-9))
                self.ax2.plot(xg, mu, color='gray', alpha=a * 0.6, lw=0.8)
        # current
        cmap = colormaps['tab10']
        for i in range(len(self.c)):
            mu = np.exp(-((xg - self.c[i])**2) / (2 * self.sigma[i]**2 + 1e-9))
            self.ax2.plot(xg, mu, color=cmap(i), lw=2.2, label=f'MF{i+1}')
        self.ax2.set_title(f"Membership Function Evolution  (N = {len(self.c)} MF)")
        self.ax2.set_ylim(0, 1.18); self.ax2.grid(alpha=0.3)
        self.ax2.legend(fontsize=7, ncol=4, loc='upper right')

        self.canvas.draw_idle()
        if self.losses:
            mse = self.losses[-1]
            self.loss_bar['value'] = float(np.clip(100 * (1 - min(1, mse / 0.5)), 0, 100))

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Train")

    def loop(self):
        if not self.running: return
        self.train_step(5); self.draw()
        self.status.config(text=f"Epoch: {self.epoch} | MSE: {self.losses[-1]:.3e}")
        if self.epoch > 3000:
            self.running = False; self.btn.config(text="▶ Train"); return
        self.after(50, self.loop)


# ============================================================
#  TAB 5: PSO
# ============================================================
class PSOTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter Studi Kasus", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="PSO — Auto-tuning PID", font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=10, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "PSO = Particle Swarm Optimization.\n"
            "Setiap 'partikel' adalah vektor (Kp,Ki,Kd).\n"
            "Partikel bergerak mengikuti:\n"
            "  v ← w·v + c1·r1·(pbest − x) + c2·r2·(gbest − x)\n\n"
            "Studi kasus: dibandingkan dengan GA —\n"
            "PSO sering konvergen lebih cepat karena\n"
            "informasi gbest langsung menyebar.\n\n"
            "Slider: w (inertia), c1, c2, jumlah partikel.")
        info.config(state=tk.DISABLED)

        self.w_var = tk.DoubleVar(value=0.7)
        self.c1_var = tk.DoubleVar(value=1.5)
        self.c2_var = tk.DoubleVar(value=1.5)
        self.n_var = tk.IntVar(value=25)
        self.damp_var = tk.DoubleVar(value=2.0)

        for label, var, lo, hi, fmt in [
            ("Inertia w", self.w_var, 0.1, 1.0, "{:.2f}"),
            ("c1 (cognitive)", self.c1_var, 0.1, 3.0, "{:.2f}"),
            ("c2 (social)", self.c2_var, 0.1, 3.0, "{:.2f}"),
            ("Jumlah partikel", self.n_var, 5, 60, "{:d}"),
            ("Plant damping d", self.damp_var, 0.5, 4.0, "{:.2f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=16).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=150).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Optimize", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Iter: 0 | gbest fit: --", font=("Courier", 9))
        self.status.pack()
        self.best_lbl = ttk.Label(left, text="Kp=-- Ki=-- Kd=--", font=("Courier", 9))
        self.best_lbl.pack()
        self.fit_bar = ttk.Progressbar(left, length=260, maximum=100)
        self.fit_bar.pack(pady=4)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.reset()

    def fitness(self, pos):
        d = self.damp_var.get()
        _, _, iae = simulate_pid_plant(*pos, damping=d)
        return 1.0 / (1.0 + iae)

    def reset(self):
        n = self.n_var.get()
        self.pos = np.random.uniform([0, 0, 0], [10, 5, 5], (n, 3))
        self.vel = np.random.uniform(-0.5, 0.5, (n, 3))
        self.pbest = self.pos.copy()
        self.pbest_fit = np.array([self.fitness(p) for p in self.pos])
        gi = int(np.argmax(self.pbest_fit))
        self.gbest = self.pbest[gi].copy()
        self.gbest_fit = float(self.pbest_fit[gi])
        self.iter = 0
        self.fit_hist = [self.gbest_fit]
        self.draw()

    def step(self):
        w = self.w_var.get(); c1 = self.c1_var.get(); c2 = self.c2_var.get()
        r1 = np.random.rand(*self.pos.shape)
        r2 = np.random.rand(*self.pos.shape)
        self.vel = (w * self.vel
                    + c1 * r1 * (self.pbest - self.pos)
                    + c2 * r2 * (self.gbest[None, :] - self.pos))
        self.pos = np.clip(self.pos + self.vel, [0, 0, 0], [10, 5, 5])
        fits = np.array([self.fitness(p) for p in self.pos])
        improved = fits > self.pbest_fit
        self.pbest[improved] = self.pos[improved]
        self.pbest_fit[improved] = fits[improved]
        gi = int(np.argmax(self.pbest_fit))
        if self.pbest_fit[gi] > self.gbest_fit:
            self.gbest = self.pbest[gi].copy()
            self.gbest_fit = float(self.pbest_fit[gi])
        self.iter += 1
        self.fit_hist.append(self.gbest_fit)

    def draw(self):
        t, y, iae = simulate_pid_plant(*self.gbest, damping=self.damp_var.get())

        self.ax1.clear()
        self.ax1.plot(t, y, 'b-', lw=2, label='y(t)')
        self.ax1.axhline(1.0, color='r', ls='--', lw=1.2, label='Setpoint')
        self.ax1.set_ylim(-0.2, 1.6)
        self.ax1.set_title(f"Respons Step — PID Terbaik PSO (iter {self.iter})")
        self.ax1.set_xlabel("Waktu (s)"); self.ax1.set_ylabel("Output")
        self.ax1.grid(alpha=0.3); self.ax1.legend(fontsize=8)

        self.ax2.clear()
        self.ax2.plot(self.fit_hist, 'm-o', lw=1.6, ms=4, label='gbest fitness')
        self.ax2.set_xlabel("Iterasi"); self.ax2.set_ylabel("Fitness")
        self.ax2.set_title("Konvergensi PSO")
        self.ax2.grid(alpha=0.3); self.ax2.legend(fontsize=8)
        self.canvas.draw_idle()

        self.best_lbl.config(
            text=f"Kp={self.gbest[0]:.3f}  Ki={self.gbest[1]:.3f}  Kd={self.gbest[2]:.3f}")
        self.fit_bar['value'] = float(np.clip(self.gbest_fit * 100, 0, 100))

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Optimize")

    def loop(self):
        if not self.running: return
        for _ in range(3):
            self.step()
        self.draw()
        self.status.config(text=f"Iter: {self.iter} | gbest fit: {self.gbest_fit:.4f}")
        if self.iter > 100:
            self.running = False; self.btn.config(text="▶ Optimize"); return
        self.after(50, self.loop)

    def export(self):
        rows = [(i, round(f, 5)) for i, f in enumerate(self.fit_hist)]
        export_csv(self, ["iterasi", "gbest_fitness"], rows,
                   f"pso_log_{datetime.now():%Y%m%d_%H%M}.csv")

# ============================================================
#  TAB: PSO 3D SWARM VISUALIZATION
# ============================================================
class PSO3DTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter & Kontrol", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="PSO 3D — Auto-tuning PID",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=11, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "Visualisasi swarm PSO dalam ruang 3D (Kp,Ki,Kd).\n\n"
            "Warna partikel = fitness (terang = lebih baik).\n"
            "Bintang merah = gbest saat ini.\n"
            "Garis oranye = jejak gbest tiap iterasi.\n\n"
            "Coba:\n"
            "  • Drag mouse di plot untuk rotate view\n"
            "  • Scroll untuk zoom\n"
            "  • Ubah w, c1, c2 untuk lihat efeknya pada\n"
            "    'penyebaran' swarm (eksplorasi vs eksploitasi)\n"
            "  • Klik ➕ Particle untuk tambah partikel saat\n"
            "    swarm sedang berjalan\n"
            "  • 📸 PNG untuk screenshot ke laporan")
        info.config(state=tk.DISABLED)

        self.w_var = tk.DoubleVar(value=0.7)
        self.c1_var = tk.DoubleVar(value=1.5)
        self.c2_var = tk.DoubleVar(value=1.5)
        self.n_var = tk.IntVar(value=25)
        self.damp_var = tk.DoubleVar(value=2.0)
        self.rot_var = tk.BooleanVar(value=True)
        self.rot_speed_var = tk.DoubleVar(value=1.5)

        for label, var, lo, hi, fmt in [
            ("Inertia w", self.w_var, 0.1, 1.0, "{:.2f}"),
            ("c1 cognitive", self.c1_var, 0.1, 3.0, "{:.2f}"),
            ("c2 social", self.c2_var, 0.1, 3.0, "{:.2f}"),
            ("N partikel", self.n_var, 5, 60, "{:d}"),
            ("Plant damping", self.damp_var, 0.5, 4.0, "{:.2f}"),
            ("Rotate speed", self.rot_speed_var, 0.0, 5.0, "{:.1f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=140).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        ttk.Checkbutton(left, text="Auto-rotate view",
                        variable=self.rot_var).pack(anchor="w", pady=4)

        row = ttk.Frame(left); row.pack(pady=6)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Start", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="➕ Particle", command=self.add_particle).pack(side=tk.LEFT, padx=2)
        row2 = ttk.Frame(left); row2.pack(pady=2)
        ttk.Button(row2, text="📸 PNG", command=self.snapshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Iter: 0 | gbest fit: --",
                                font=("Courier", 9))
        self.status.pack(pady=2)
        self.best_lbl = ttk.Label(left, text="Kp=-- Ki=-- Kd=--",
                                  font=("Courier", 9))
        self.best_lbl.pack()
        self.fit_bar = ttk.Progressbar(left, length=260, maximum=100)
        self.fit_bar.pack(pady=4)
        self.fit_lbl = ttk.Label(left, text="gbest fitness", font=("Courier", 9))
        self.fit_lbl.pack()

        # 3D plot
        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 7), dpi=80)
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._azim = 30.0
        self.reset()

    def fitness(self, pos):
        _, _, iae = simulate_pid_plant(*pos, damping=self.damp_var.get())
        return 1.0 / (1.0 + iae)

    def reset(self):
        n = self.n_var.get()
        self.pos = np.random.uniform([0, 0, 0], [10, 5, 5], (n, 3))
        self.vel = np.random.uniform(-0.5, 0.5, (n, 3))
        self.pbest = self.pos.copy()
        self.pbest_fit = np.array([self.fitness(p) for p in self.pos])
        gi = int(np.argmax(self.pbest_fit))
        self.gbest = self.pbest[gi].copy()
        self.gbest_fit = float(self.pbest_fit[gi])
        self.gbest_trail = [self.gbest.copy()]
        self.iter = 0
        self.running = False
        self.draw()

    def step(self):
        w = self.w_var.get(); c1 = self.c1_var.get(); c2 = self.c2_var.get()
        r1 = np.random.rand(*self.pos.shape)
        r2 = np.random.rand(*self.pos.shape)
        self.vel = (w * self.vel
                    + c1 * r1 * (self.pbest - self.pos)
                    + c2 * r2 * (self.gbest[None, :] - self.pos))
        self.pos = np.clip(self.pos + self.vel, [0, 0, 0], [10, 5, 5])
        fits = np.array([self.fitness(p) for p in self.pos])
        imp = fits > self.pbest_fit
        self.pbest[imp] = self.pos[imp]
        self.pbest_fit[imp] = fits[imp]
        gi = int(np.argmax(self.pbest_fit))
        if self.pbest_fit[gi] > self.gbest_fit:
            self.gbest = self.pbest[gi].copy()
            self.gbest_fit = float(self.pbest_fit[gi])
            self.gbest_trail.append(self.gbest.copy())
            if len(self.gbest_trail) > 250:
                self.gbest_trail.pop(0)
        self.iter += 1

    def add_particle(self):
        new_pos = np.random.uniform([0, 0, 0], [10, 5, 5])
        new_vel = np.random.uniform(-0.5, 0.5, 3)
        self.pos = np.vstack([self.pos, new_pos])
        self.vel = np.vstack([self.vel, new_vel])
        self.pbest = np.vstack([self.pbest, new_pos])
        f = self.fitness(new_pos)
        self.pbest_fit = np.append(self.pbest_fit, f)
        if f > self.gbest_fit:
            self.gbest = new_pos.copy(); self.gbest_fit = f
            self.gbest_trail.append(self.gbest.copy())
        self.draw()

    def draw(self):
        # Preserve user's mouse rotation
        elev, azim = self.ax.elev, self.ax.azim
        if self.rot_var.get() and not self.running:
            azim = self._azim
        self.ax.clear()

        fmin = float(self.pbest_fit.min())
        fmax = float(self.pbest_fit.max())
        rng = max(fmax - fmin, 1e-9)
        norm = (self.pbest_fit - fmin) / rng
        cmap = colormaps['viridis']

        self.ax.scatter(self.pos[:, 0], self.pos[:, 1], self.pos[:, 2],
                        c=norm, cmap=cmap, s=55, edgecolors='k',
                        linewidths=0.4, alpha=0.85)
        self.ax.scatter(*self.gbest, c='red', s=280, marker='*',
                        edgecolors='darkred', linewidths=1.5,
                        label=f'gbest ({self.gbest_fit:.4f})')
        if len(self.gbest_trail) > 1:
            tr = np.array(self.gbest_trail)
            self.ax.plot(tr[:, 0], tr[:, 1], tr[:, 2],
                         c='orange', lw=1.6, alpha=0.75, label='gbest trail')
        self.ax.set_xlabel('Kp'); self.ax.set_ylabel('Ki'); self.ax.set_zlabel('Kd')
        self.ax.set_xlim(0, 10); self.ax.set_ylim(0, 5); self.ax.set_zlim(0, 5)
        self.ax.set_title(f"PSO 3D — Iter {self.iter} | {len(self.pos)} partikel",
                          fontsize=11)
        self.ax.legend(loc='upper left', fontsize=8)

        # auto-rotate
        if self.rot_var.get():
            self._azim = (self._azim + self.rot_speed_var.get()) % 360
        self.ax.view_init(elev=max(5, min(85, elev)), azim=self._azim if self.rot_var.get() else azim)

        self.canvas.draw_idle()
        self.best_lbl.config(
            text=f"Kp={self.gbest[0]:.2f}  Ki={self.gbest[1]:.2f}  Kd={self.gbest[2]:.2f}")
        self.fit_bar['value'] = float(np.clip(self.gbest_fit * 100, 0, 100))
        self.fit_lbl.config(text=f"gbest fitness = {self.gbest_fit:.4f}")

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Start")

    def loop(self):
        if not self.running: return
        for _ in range(2):
            self.step()
        self.draw()
        self.status.config(text=f"Iter: {self.iter} | gbest fit: {self.gbest_fit:.4f}")
        if self.iter > 200:
            self.running = False; self.btn.config(text="▶ Start"); return
        self.after(80, self.loop)

    def snapshot(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=f"pso3d_iter{self.iter}.png",
            filetypes=[("PNG", "*.png")])
        if path:
            self.fig.savefig(path, dpi=150, bbox_inches='tight')
            messagebox.showinfo("OK", f"Snapshot: {path}")

    def export(self):
        rows = [(i, round(float(f), 5))
                for i, f in enumerate([self.gbest_fit])]
        # trail export
        rows = [(i, round(float(p[0]), 4), round(float(p[1]), 4),
                 round(float(p[2]), 4)) for i, p in enumerate(self.gbest_trail)]
        export_csv(self, ["iter", "Kp", "Ki", "Kd"], rows,
                   f"pso3d_trail_{datetime.now():%Y%m%d_%H%M}.csv")

# ============================================================
#  TAB: PENDULUM ANIMATION
# ============================================================
class PendulumTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Kontroler PID & Plant", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="Animasi Inverted Pendulum",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=44, height=9, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "Simulasi visual cart-pole yang dikontrol PID.\n"
            "Tongkat harus tetap tegak — jika |θ|>70°,\n"
            "sistem jatuh.\n\n"
            "Interaksi:\n"
            "  • Slider Kp/Ki/Kd → lihat efek tuning live\n"
            "  • 💥 Push! → impuls gangguan seperti\n"
            "    seseorang menyenggol tongkat\n"
            "  • 🎲 Randomize → θ awal acak\n"
            "  • 📈 Auto-tune → GA cari PID dalam 2 detik\n\n"
            "Amati: terlalu besar Kp → osilasi.\n"
            "Terlalu kecil → jatuh lambat.")
        info.config(state=tk.DISABLED)

        self.kp_var = tk.DoubleVar(value=40)
        self.ki_var = tk.DoubleVar(value=2)
        self.kd_var = tk.DoubleVar(value=12)
        self.g_var = tk.DoubleVar(value=9.81)
        self.L_var = tk.DoubleVar(value=1.0)
        self.dist_var = tk.DoubleVar(value=0.0)
        self.noise_var = tk.DoubleVar(value=0.0)

        for label, var, lo, hi, fmt in [
            ("Kp", self.kp_var, 0, 120, "{:.1f}"),
            ("Ki", self.ki_var, 0, 30, "{:.2f}"),
            ("Kd", self.kd_var, 0, 40, "{:.1f}"),
            ("Gravity g", self.g_var, 1, 20, "{:.2f}"),
            ("Pole length L", self.L_var, 0.3, 2.0, "{:.2f}"),
            ("Ext. torque", self.dist_var, -3, 3, "{:.2f}"),
            ("Sensor noise", self.noise_var, 0, 0.2, "{:.3f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=13).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=150).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Start", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="💥 Push!", command=self.push).pack(side=tk.LEFT, padx=2)
        row2 = ttk.Frame(left); row2.pack(pady=2)
        ttk.Button(row2, text="🎲 Randomize", command=self.randomize).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="📈 Auto-tune GA", command=self.autotune_ga).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="θ=--  ω=--  F=--",
                                font=("Courier", 9))
        self.status.pack(pady=4)
        ttk.Label(left, text="Gaya kontrol (F):").pack()
        self.force_bar = ttk.Progressbar(left, length=260, maximum=100)
        self.force_bar.pack(pady=2)
        self.state_lbl = ttk.Label(left, text="Status: siap",
                                   font=("Arial", 10, "bold"), foreground="gray")
        self.state_lbl.pack(pady=2)

        # Canvas
        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(right, bg='#f0f4f8', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind('<Configure>', lambda e: self._redraw())

        # State
        self.theta = 0.15
        self.omega = 0.0
        self.x_cart = 0.0
        self.v_cart = 0.0
        self.e_int = 0.0
        self.e_prev = 0.0
        self.t = 0.0
        self.u = 0.0
        self.trail = []

    def _redraw(self):
        self.canvas.delete("bg")
        W = self.canvas.winfo_width(); H = self.canvas.winfo_height()
        if W < 10: return
        # Track
        y_track = H * 0.78
        self.canvas.create_rectangle(0, y_track, W, y_track + 8,
                                     fill='#c8d4e0', outline='', tags='bg')
        self.canvas.create_line(0, y_track, W, y_track,
                                fill='#7f8fa0', width=1, tags='bg')
        # Ruler marks
        for i in range(0, W, 40):
            self.canvas.create_line(i, y_track + 8, i, y_track + 14,
                                    fill='#7f8fa0', tags='bg')
        # Title
        self.canvas.create_text(W - 12, 20, text="Cart-Pole PID Animation",
                                anchor='e', fill='#556677',
                                font=('Arial', 11, 'bold'), tags='bg')

    def _draw(self):
        self.canvas.delete("dyn")
        W = self.canvas.winfo_width(); H = self.canvas.winfo_height()
        if W < 10: return

        y_track = H * 0.78
        cx = W / 2 + self.x_cart
        cy = y_track

        # Ghost trail of cart
        self.trail.append((cx, cy))
        if len(self.trail) > 60:
            self.trail.pop(0)
        for i, (tx, ty) in enumerate(self.trail):
            a = i / len(self.trail)
            self.canvas.create_oval(tx - 4, ty - 4, tx + 4, ty + 4,
                                    fill='', outline=f'#{int(200 - a*120):02x}'
                                    f'{int(200 - a*80):02x}ff',
                                    width=1, tags='dyn')

        cart_w, cart_h = 66, 28
        # Cart body
        self.canvas.create_rectangle(cx - cart_w/2, cy - cart_h/2,
                                     cx + cart_w/2, cy + cart_h/2,
                                     fill='#3d6fa5', outline='#1e3c5c',
                                     width=2, tags='dyn')
        # Wheels
        for wx in [cx - cart_w/2 + 12, cx + cart_w/2 - 12]:
            self.canvas.create_oval(wx - 7, cy + cart_h/2 - 7,
                                    wx + 7, cy + cart_h/2 + 7,
                                    fill='#2c3e50', outline='#111', tags='dyn')

        # Pole
        Lpx = self.L_var.get() * 130
        px = cx + Lpx * np.sin(self.theta)
        py = cy - cart_h/2 - Lpx * np.cos(self.theta)
        # Reference vertical line
        self.canvas.create_line(cx, cy - cart_h/2, cx, cy - cart_h/2 - Lpx,
                                fill='#bbb', width=1, dash=(4, 3), tags='dyn')
        # Pole itself
        self.canvas.create_line(cx, cy - cart_h/2, px, py,
                                fill='#c0392b', width=7,
                                capstyle='round', tags='dyn')
        # Bob
        self.canvas.create_oval(px - 11, py - 11, px + 11, py + 11,
                                fill='#e74c3c', outline='#7a2418',
                                width=2, tags='dyn')

        # Angle arc
        r_arc = 45
        self.canvas.create_arc(cx - r_arc, cy - cart_h/2 - r_arc,
                               cx + r_arc, cy - cart_h/2 + r_arc,
                               start=90, extent=-np.degrees(self.theta),
                               style='arc', outline='#e67e22',
                               width=2, tags='dyn')

        # Angle text
        deg = np.degrees(self.theta)
        color = '#27ae60' if abs(deg) < 15 else ('#e67e22' if abs(deg) < 40 else '#c0392b')
        self.canvas.create_text(cx, cy + cart_h/2 + 32,
                                text=f"θ = {deg:+.1f}°",
                                fill=color, font=('Courier', 12, 'bold'), tags='dyn')

        # Force arrow
        if abs(self.u) > 0.8:
            al = float(np.clip(self.u * 0.9, -90, 90))
            ya = cy - cart_h/2 - 12
            self.canvas.create_line(cx, ya, cx + al, ya,
                                    fill='#16a085', width=4,
                                    arrow=tk.LAST, arrowshape=(11, 13, 5),
                                    tags='dyn')
            self.canvas.create_text(cx + al/2, ya - 12,
                                    text=f"F = {self.u:+.1f} N",
                                    fill='#16a085', font=('Courier', 9),
                                    tags='dyn')

    def reset(self):
        self.theta = 0.15
        self.omega = 0.0
        self.x_cart = 0.0
        self.v_cart = 0.0
        self.e_int = 0.0
        self.e_prev = 0.0
        self.t = 0.0
        self.u = 0.0
        self.trail = []
        self.running = False
        if hasattr(self, 'btn'):
            self.btn.config(text="▶ Start")
        self.state_lbl.config(text="Status: siap", foreground="gray")
        self._redraw()
        self._draw()

    def push(self):
        self.omega += np.random.choice([-1, 1]) * 1.8

    def randomize(self):
        self.theta = np.random.uniform(-0.25, 0.25)
        self.omega = 0.0

    def autotune_ga(self):
        """GA cepat: cari PID dalam ~50 generasi."""
        pop_size = 20
        pop = np.random.uniform([10, 0, 0], [80, 20, 25], (pop_size, 3))
        g = self.g_var.get(); L = self.L_var.get()
        for _ in range(40):
            fits = np.empty(pop_size)
            for i, ind in enumerate(pop):
                _, _, iae = self._simulate_full(ind[0], ind[1], ind[2], g, L)
                fits[i] = 1.0 / (1.0 + iae)
            bi = int(np.argmax(fits))
            new = [pop[bi].copy()]
            while len(new) < pop_size:
                i1, i2 = np.random.choice(pop_size, 2, replace=False)
                p1 = pop[i1] if fits[i1] > fits[i2] else pop[i2]
                i3, i4 = np.random.choice(pop_size, 2, replace=False)
                p2 = pop[i3] if fits[i3] > fits[i4] else pop[i4]
                a = np.random.rand(3)
                c = a * p1 + (1 - a) * p2
                if np.random.rand() < 0.3:
                    c += np.random.randn(3) * [3, 0.5, 1.5]
                new.append(np.clip(c, [0, 0, 0], [120, 30, 40]))
            pop = np.array(new)
        best = pop[int(np.argmax(fits))]
        self.kp_var.set(round(float(best[0]), 1))
        self.ki_var.set(round(float(best[1]), 2))
        self.kd_var.set(round(float(best[2]), 1))
        messagebox.showinfo("Auto-tune GA",
                            f"PID ditemukan:\n"
                            f"Kp={best[0]:.2f}  Ki={best[1]:.2f}  Kd={best[2]:.2f}")

    def _simulate_full(self, Kp, Ki, Kd, g, L):
        """Simulasi pendulum dari theta=0.15 sampai jatuh."""
        th, om = 0.15, 0.0
        ei, ep = 0.0, 0.0
        dt = 0.02
        iae = 0.0
        for _ in range(500):
            e = -th
            ei += e * dt
            de = (e - ep) / dt
            u = float(np.clip(Kp * e + Ki * ei + Kd * de, -100, 100))
            acc = (g / L) * np.sin(th) - (u / L) * np.cos(th) - 0.5 * om
            om += acc * dt
            th += om * dt
            iae += abs(th) * dt
            ep = e
            if abs(th) > 1.2:
                iae += 100.0 * (500 * dt - iae)
                break
        return None, None, iae

    def step(self):
        dt = 0.03
        noise = self.noise_var.get()
        th_meas = self.theta + (np.random.randn() * noise if noise > 0 else 0)

        e = -th_meas
        self.e_int += e * dt
        de = (e - self.e_prev) / dt
        u = (self.kp_var.get() * e
             + self.ki_var.get() * self.e_int
             + self.kd_var.get() * de)
        u = float(np.clip(u, -100, 100))
        self.u = u
        self.e_prev = e

        g = self.g_var.get()
        L = self.L_var.get()
        dist = self.dist_var.get()
        acc = (g / L) * np.sin(self.theta) - (u / L) * np.cos(self.theta) \
              - 0.5 * self.omega + dist
        self.omega += acc * dt
        self.theta += self.omega * dt

        # Cart movement (visual only, tanpa feedback posisi)
        self.v_cart += u * dt * 0.35
        self.v_cart *= 0.94
        self.x_cart += self.v_cart
        W = self.canvas.winfo_width() or 700
        mx = W / 2 - 90
        if abs(self.x_cart) > mx:
            self.x_cart = np.sign(self.x_cart) * mx
            self.v_cart = -self.v_cart * 0.4

        self.t += dt

        # Fall detection
        if abs(self.theta) > 1.2:
            self.running = False
            self.btn.config(text="▶ Start")
            self.state_lbl.config(text=f"Status: JATUH di t={self.t:.1f}s",
                                  foreground="#c0392b")

        self._draw()
        self.status.config(text=f"θ={np.degrees(self.theta):+6.1f}°  "
                                f"ω={self.omega:+.2f}  F={u:+6.1f}N  "
                                f"t={self.t:.1f}s")
        self.force_bar['value'] = float(np.clip((u + 100) / 2, 0, 100))

    def toggle(self):
        if not self.running and abs(self.theta) > 1.0:
            self.reset()
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause")
            self.state_lbl.config(text="Status: berjalan", foreground="#27ae60")
            self.loop()
        else:
            self.btn.config(text="▶ Start")
            self.state_lbl.config(text="Status: pause", foreground="#e67e22")

    def loop(self):
        if not self.running: return
        for _ in range(2):
            self.step()
            if not self.running: return
        self.after(30, self.loop)


# ============================================================
#  TAB 6: REINFORCEMENT LEARNING
# ============================================================
class RLTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="RL — Q-Learning Inverted Pendulum",
                  font=("Arial", 12, "bold")).pack(pady=4)

        info = tk.Text(left, width=46, height=10, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "Agent belajar menjaga tongkat tetap tegak.\n"
            "State = (θ, ω) didiskretkan 12×12.\n"
            "Action = {−τ, 0, +τ}.\n"
            "Reward +1 jika |θ| < 0.2, episode berakhir\n"
            "jika |θ| > 0.6.\n\n"
            "Studi kasus: kontrol adaptif tanpa model\n"
            "plant — bandingkan dengan PID yang butuh\n"
            "model eksak.\n\n"
            "Amati: reward total per episode NAIK seiring\n"
            "agent belajar; epsilon turun (eksplorasi→\n"
            "eksploitasi).")
        info.config(state=tk.DISABLED)

        self.alpha_var = tk.DoubleVar(value=0.2)
        self.gamma_var = tk.DoubleVar(value=0.95)
        self.eps_decay_var = tk.DoubleVar(value=0.995)
        self.torque_var = tk.DoubleVar(value=4.0)

        for label, var, lo, hi, fmt in [
            ("α (learning)", self.alpha_var, 0.01, 0.5, "{:.2f}"),
            ("γ (discount)", self.gamma_var, 0.5, 0.999, "{:.3f}"),
            ("ε decay", self.eps_decay_var, 0.9, 1.0, "{:.3f}"),
            ("Max torque τ", self.torque_var, 2.0, 8.0, "{:.1f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=150).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write", lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Train (fast)", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⤓ CSV", command=self.export).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="▶ Test Policy", command=self.test_policy).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(left, text="Episode: 0 | ε=1.00 | R=--",
                                font=("Courier", 9))
        self.status.pack()
        self.rew_bar = ttk.Progressbar(left, length=260, maximum=300)
        self.rew_bar.pack(pady=4)
        self.rew_lbl = ttk.Label(left, text="Reward episode terakhir", font=("Courier", 9))
        self.rew_lbl.pack()

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.reset()

    # --- discretization ---
    def discretize(self, theta, omega):
        n = 12
        ti = int(np.clip((theta + 0.6) / 1.2 * (n - 1), 0, n - 1))
        wi = int(np.clip((omega + 4.0) / 8.0 * (n - 1), 0, n - 1))
        return ti, wi

    def reset(self):
        self.Q = np.zeros((12, 12, 3))
        self.alpha = self.alpha_var.get()
        self.eps = 1.0
        self.episode = 0
        self.reward_hist = []
        self.running = False
        self.draw_learning()
        self.draw_pendulum(0.0)
        self.canvas.draw()

    def run_episode(self, train=True):
        theta = np.random.uniform(-0.1, 0.1)
        omega = 0.0
        total_r = 0.0
        max_steps = 300
        dt = 0.02
        torque_amp = self.torque_var.get()
        tau_map = [-torque_amp, 0.0, torque_amp]

        for step in range(max_steps):
            ti, wi = self.discretize(theta, omega)
            if train and np.random.rand() < self.eps:
                a = np.random.randint(3)
            else:
                a = int(np.argmax(self.Q[ti, wi, :]))
            tau = tau_map[a]
            # dynamics
            alpha = 10.0 * np.sin(theta) - 0.3 * omega + tau
            omega += alpha * dt
            theta += omega * dt
            reward = 1.0 if abs(theta) < 0.2 else 0.0
            done = abs(theta) > 0.6
            if done:
                reward = -10.0
            ti2, wi2 = self.discretize(theta, omega)
            if train:
                best_next = np.max(self.Q[ti2, wi2, :])
                target = reward + (0 if done else self.gamma_var.get() * best_next)
                self.Q[ti, wi, a] += self.alpha_var.get() * (target - self.Q[ti, wi, a])
            total_r += reward
            if done:
                break
        if train:
            self.eps *= self.eps_decay_var.get()
            self.episode += 1
            self.reward_hist.append(total_r)
        return total_r, theta

    def draw_learning(self):
        self.ax1.clear()
        if self.reward_hist:
            # moving average
            w = 20
            sm = np.convolve(self.reward_hist, np.ones(w) / w, mode='valid')
            self.ax1.plot(self.reward_hist, 'lightsteelblue', lw=0.7, alpha=0.7, label='reward')
            self.ax1.plot(np.arange(w - 1, len(self.reward_hist)), sm,
                          'b-', lw=2, label=f'MA({w})')
            self.ax1.set_title(f"Learning Curve — episode {self.episode}, ε={self.eps:.3f}")
            self.ax1.legend(fontsize=8)
        else:
            self.ax1.set_title("Learning Curve (klik 'Train' untuk mulai)")
        self.ax1.set_xlabel("Episode"); self.ax1.set_ylabel("Total reward")
        self.ax1.grid(alpha=0.3)

        self.ax2.clear()
        self.ax2.imshow(np.max(self.Q, axis=2), aspect='auto', origin='lower',
                        extent=[-4, 4, -0.6, 0.6], cmap='viridis')
        self.ax2.set_xlabel("ω (rad/s)"); self.ax2.set_ylabel("θ (rad)")
        self.ax2.set_title("Q-value (max over actions)")
        self.canvas.draw_idle()

        if self.reward_hist:
            last = self.reward_hist[-1]
            self.rew_bar['value'] = float(np.clip(last, 0, 300))
            self.rew_lbl.config(text=f"Reward ep. terakhir: {last:.1f}")

    def draw_pendulum(self, theta):
        ax = self.fig.axes[0]  # tidak dipakai; gunakan kanvas terpisah
        # Kita tampilkan di learning plot sebagai inset? Simpel: skip visual pendulum di figure
        # dan ganti dengan indikator teks.
        pass

    def test_policy(self):
        theta = 0.1
        omega = 0.0
        total = 0.0
        for step in range(300):
            ti, wi = self.discretize(theta, omega)
            a = int(np.argmax(self.Q[ti, wi, :]))
            tau = [-self.torque_var.get(), 0.0, self.torque_var.get()][a]
            alpha = 10.0 * np.sin(theta) - 0.3 * omega + tau
            omega += alpha * 0.02
            theta += omega * 0.02
            total += 1.0 if abs(theta) < 0.2 else 0.0
            if abs(theta) > 0.6:
                break
        messagebox.showinfo("Test Policy",
                            f"θ akhir = {theta:.3f} rad\n"
                            f"Total reward uji = {total:.1f}\n"
                            f"Steps survived = {step+1}")

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Train (fast)")

    def loop(self):
        if not self.running: return
        for _ in range(10):
            self.run_episode(train=True)
        self.draw_learning()
        self.status.config(text=f"Episode: {self.episode} | ε={self.eps:.3f} | "
                                f"R={self.reward_hist[-1]:.1f}")
        if self.episode > 1500:
            self.running = False; self.btn.config(text="▶ Train (fast)"); return
        self.after(50, self.loop)

    def export(self):
        rows = [(i + 1, round(r, 3)) for i, r in enumerate(self.reward_hist)]
        export_csv(self, ["episode", "total_reward"], rows,
                   f"rl_log_{datetime.now():%Y%m%d_%H%M}.csv")

# ============================================================
#  TAB: FUZZY CONTROL SURFACE 3D
# ============================================================
class FuzzySurfaceTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Parameter", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="Fuzzy Control Surface 3D",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=44, height=10, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "Permukaan kontrol z = u(e, Δe) dari rule base\n"
            "3×3 yang sama dengan tab Fuzzy sebelumnya.\n\n"
            "Cara membaca:\n"
            "  • Sumbu X = error e\n"
            "  • Sumbu Y = perubahan error Δe\n"
            "  • Sumbu Z = output heater (%)\n\n"
            "Titik merah = 'operator' yang bisa Anda gerakkan\n"
            "dengan slider di bawah — lihat bagaimana\n"
            "permukaan menghasilkan output.\n\n"
            "Drag mouse untuk memutar view 3D.\n"
            "Bandingkan bentuk permukaan untuk rule base\n"
            "yang berbeda → mahasiswa paham 'bentuk'\n"
            "kontroler fuzzy secara visual.")
        info.config(state=tk.DISABLED)

        self.e_var = tk.DoubleVar(value=0.3)
        self.de_var = tk.DoubleVar(value=0.0)
        self.res_var = tk.IntVar(value=25)
        self.show_mesh = tk.BooleanVar(value=True)
        self.show_wire = tk.BooleanVar(value=False)

        for label, var, lo, hi, fmt in [
            ("e (error)", self.e_var, -1.2, 1.2, "{:+.2f}"),
            ("Δe (delta error)", self.de_var, -1.2, 1.2, "{:+.2f}"),
            ("Grid resolution", self.res_var, 10, 60, "{:d}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=140).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        ttk.Checkbutton(left, text="Tampilkan surface",
                        variable=self.show_mesh).pack(anchor="w")
        ttk.Checkbutton(left, text="Wireframe overlay",
                        variable=self.show_wire).pack(anchor="w")

        ttk.Button(left, text="⟲ Redraw", command=self.draw).pack(pady=8)
        ttk.Button(left, text="📸 Snapshot PNG", command=self.snapshot).pack(pady=2)

        # Readouts
        self.out_frame = ttk.LabelFrame(left, text="Output Fuzzy", padding=6)
        self.out_frame.pack(fill=tk.X, pady=8)
        self.out_lbl = ttk.Label(self.out_frame,
                                 text="u = --",
                                 font=("Courier", 12, "bold"),
                                 foreground="navy")
        self.out_lbl.pack()
        self.membership_lbl = ttk.Label(self.out_frame, text="",
                                        font=("Courier", 8), justify=tk.LEFT)
        self.membership_lbl.pack()
        self.out_bar = ttk.Progressbar(self.out_frame, length=240, maximum=100)
        self.out_bar.pack(pady=4)

        # Plot
        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 7), dpi=80)
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.draw()

    # --- fuzzy core (sama seperti FuzzyTab) ---
    @staticmethod
    def tri(x, a, b, c):
        y = np.zeros_like(x, dtype=float)
        if b > a:
            m = (x >= a) & (x < b); y[m] = (x[m] - a) / (b - a)
        if c > b:
            m = (x > b) & (x <= c); y[m] = (c - x[m]) / (c - b)
        y[x == b] = 1.0
        return y

    def fuzzify(self, e, de):
        eF = (self.tri(np.array([e]), -1.2, -1.0, -0.2)[0],
              self.tri(np.array([e]), -0.5, 0.0, 0.5)[0],
              self.tri(np.array([e]), 0.2, 1.0, 1.2)[0])
        dF = (self.tri(np.array([de]), -1.2, -1.0, -0.2)[0],
              self.tri(np.array([de]), -0.5, 0.0, 0.5)[0],
              self.tri(np.array([de]), 0.2, 1.0, 1.2)[0])
        return eF, dF

    def infer(self, e, de):
        eF, dF = self.fuzzify(e, de)
        eN, eZ, eP = eF; dN, dZ, dP = dF
        rules = [(eN,dN,-1.0),(eN,dZ,-1.0),(eN,dP,-0.5),
                 (eZ,dN,-1.0),(eZ,dZ,0.0),(eZ,dP,0.5),
                 (eP,dN,0.5),(eP,dZ,1.0),(eP,dP,1.0)]
        wsum = vsum = 0.0
        for we, wd, out in rules:
            w = min(we, wd); wsum += w; vsum += w * out
        return vsum / wsum if wsum > 1e-9 else 0.0

    def draw(self):
        elev, azim = self.ax.elev, self.ax.azim
        self.ax.clear()

        N = self.res_var.get()
        e = np.linspace(-1.2, 1.2, N)
        de = np.linspace(-1.2, 1.2, N)
        E, DE = np.meshgrid(e, de)
        U = np.zeros_like(E)
        for i in range(N):
            for j in range(N):
                U[i, j] = (self.infer(E[i, j], DE[i, j]) + 1.0) * 50.0

        if self.show_mesh.get():
            cmap = colormaps['coolwarm']
            self.ax.plot_surface(E, DE, U, cmap=cmap, alpha=0.85,
                                 edgecolor='none', antialiased=True)
        if self.show_wire.get():
            self.ax.plot_wireframe(E, DE, U, color='k',
                                   linewidth=0.4, alpha=0.5)

        # Current operating point
        e0 = self.e_var.get(); de0 = self.de_var.get()
        u0_norm = self.infer(e0, de0)
        u0 = (u0_norm + 1.0) * 50.0
        self.ax.scatter([e0], [de0], [u0], c='red', s=120,
                        edgecolors='darkred', linewidths=2, zorder=10)
        # Vertical drop line
        self.ax.plot([e0, e0], [de0, de0], [0, u0],
                     'r--', lw=1, alpha=0.7)

        self.ax.set_xlabel('e (error)')
        self.ax.set_ylabel('Δe')
        self.ax.set_zlabel('u (%)')
        self.ax.set_zlim(0, 100)
        self.ax.set_title("Control Surface  u = f(e, Δe)", fontsize=11)
        self.ax.view_init(elev=elev, azim=azim)
        self.canvas.draw_idle()

        # Readouts
        eF, dF = self.fuzzify(e0, de0)
        self.out_lbl.config(text=f"u = {u0:5.1f} %   (u_norm = {u0_norm:+.3f})")
        self.out_bar['value'] = u0
        self.membership_lbl.config(
            text=(f"μ(e NB,Z,PB)   = ({eF[0]:.2f}, {eF[1]:.2f}, {eF[2]:.2f})\n"
                  f"μ(Δe NB,Z,PB)  = ({dF[0]:.2f}, {dF[1]:.2f}, {dF[2]:.2f})"))

    def snapshot(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=f"fuzzy_surface_e{self.e_var.get():+.2f}.png",
            filetypes=[("PNG", "*.png")])
        if path:
            self.fig.savefig(path, dpi=150, bbox_inches='tight')
            messagebox.showinfo("OK", f"Snapshot: {path}")


# ============================================================
#  TAB: STEP RESPONSE RACE
# ============================================================
class StepRaceTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)

        left = ttk.LabelFrame(self, text="Bandingkan Kontroler", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="Race — PID vs Fuzzy vs NN",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=44, height=9, wrap=tk.WORD)
        info.pack()
        info.insert(tk.END,
            "Animasi tiga kontroler mengejar setpoint\n"
            "yang sama pada plant orde-2 yang identik.\n\n"
            "  🔵 PID       — hasil auto-tune\n"
            "  🟢 Fuzzy     — rule base Mamdani\n"
            "  🟠 PID+NN    — PID dengan gain diprediksi NN\n\n"
            "Interactive:\n"
            "  • Ubah setpoint live\n"
            "  • Ubah damping plant (simulasi keausan)\n"
            "  • Reset → lihat siapa yang menang (settling\n"
            "    paling cepat = 'race champion')\n\n"
            "Kesimpulan pedagogis: tidak ada kontroler\n"
            "yang selalu menang — tergantung karakter plant.")
        info.config(state=tk.DISABLED)

        self.sp_var = tk.DoubleVar(value=1.0)
        self.damp_var = tk.DoubleVar(value=2.0)
        self.dt_var = tk.DoubleVar(value=0.03)

        for label, var, lo, hi, fmt in [
            ("Setpoint", self.sp_var, 0.3, 1.5, "{:.2f}"),
            ("Plant damping", self.damp_var, 0.5, 4.0, "{:.2f}"),
            ("Anim speed", self.dt_var, 0.01, 0.1, "{:.3f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=140).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: l.config(text=f.format(v.get())))

        row = ttk.Frame(left); row.pack(pady=8)
        self.running = False
        self.btn = ttk.Button(row, text="▶ Start", command=self.toggle)
        self.btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="⟲ Reset", command=self.reset).pack(side=tk.LEFT, padx=2)

        self.scoreboard = tk.Text(left, width=44, height=7, font=("Courier", 9),
                                  bg="#f5f5dc")
        self.scoreboard.pack(pady=6)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 7), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # ---- controllers ----
        self.controllers = {
            'PID':      {'color': '#2e86c1', 'params': (3.8, 3.0, 3.2)},
            'Fuzzy':    {'color': '#27ae60', 'params': None},
            'PID+NN':   {'color': '#e67e22', 'params': (2.5, 2.0, 4.0)},
        }
        self.reset()

    # ---------- fuzzy ----------
    @staticmethod
    def tri(x, a, b, c):
        y = np.zeros_like(x, dtype=float)
        if b > a:
            m = (x >= a) & (x < b); y[m] = (x[m] - a) / (b - a)
        if c > b:
            m = (x > b) & (x <= c); y[m] = (c - x[m]) / (c - b)
        y[x == b] = 1.0
        return y

    def fuzzy_u(self, e, de):
        def fz(x):
            return (self.tri(np.array([x]), -1.2, -1.0, -0.2)[0],
                    self.tri(np.array([x]), -0.5, 0.0, 0.5)[0],
                    self.tri(np.array([x]), 0.2, 1.0, 1.2)[0])
        eF = fz(e); dF = fz(de)
        eN, eZ, eP = eF; dN, dZ, dP = dF
        rules = [(eN,dN,-1.0),(eN,dZ,-1.0),(eN,dP,-0.5),
                 (eZ,dN,-1.0),(eZ,dZ,0.0),(eZ,dP,0.5),
                 (eP,dN,0.5),(eP,dZ,1.0),(eP,dP,1.0)]
        wsum = vsum = 0.0
        for we, wd, out in rules:
            w = min(we, wd); wsum += w; vsum += w * out
        return vsum / wsum if wsum > 1e-9 else 0.0

    # ---------- simulation state ----------
    def reset(self):
        self.t = 0.0
        # state x1,x2 per controller
        self.state = {k: [0.0, 0.0] for k in self.controllers}
        self.e_int = {k: 0.0 for k in self.controllers}
        self.e_prev = {k: 0.0 for k in self.controllers}
        self.settling = {k: None for k in self.controllers}
        self.hist = {k: ([], []) for k in self.controllers}
        self.t_hist = []
        self.running = False
        self.btn.config(text="▶ Start")
        self.init_plot()
        self.update_scoreboard()

    def init_plot(self):
        self.ax1.clear()
        self.ax1.set_xlim(0, 10); self.ax1.set_ylim(-0.2, 1.7)
        self.ax1.set_xlabel("Waktu (s)"); self.ax1.set_ylabel("Output")
        self.ax1.set_title("Race — 3 Kontroler, 1 Plant")
        self.ax1.grid(alpha=0.3)
        self.lines = {}
        for name, cfg in self.controllers.items():
            line, = self.ax1.plot([], [], color=cfg['color'],
                                  lw=2, label=name)
            self.lines[name] = line
        self.sp_line = self.ax1.axhline(1.0, color='k', ls='--', lw=1.2,
                                        label='Setpoint')
        self.ax1.legend(loc='lower right', fontsize=9)

        self.ax2.clear()
        self.ax2.set_xlim(0, 10); self.ax2.set_ylim(-11, 11)
        self.ax2.set_xlabel("Waktu (s)"); self.ax2.set_ylabel("u(t)")
        self.ax2.set_title("Sinyal Kontrol")
        self.ax2.grid(alpha=0.3)
        self.u_lines = {}
        for name, cfg in self.controllers.items():
            line, = self.ax2.plot([], [], color=cfg['color'], lw=1.3, alpha=0.85)
            self.u_lines[name] = line
        self.canvas.draw()

    def step(self):
        sp = self.sp_var.get()
        d = self.damp_var.get()
        dt = 0.02

        self.t += dt
        self.t_hist.append(self.t)

        for name, cfg in self.controllers.items():
            x1, x2 = self.state[name]
            e = sp - x1
            self.e_int[name] += e * dt
            de = (e - self.e_prev[name]) / dt

            if name == 'Fuzzy':
                u_norm = self.fuzzy_u(float(np.clip(e/0.5, -1.2, 1.2)),
                                      float(np.clip(de/2.0, -1.2, 1.2)))
                u = u_norm * 8.0
            else:
                Kp, Ki, Kd = cfg['params']
                # 'NN': gain diprediksi (simulasi nonlinear)
                if name == 'PID+NN':
                    Kp = Kp * (1 + 0.3 * np.tanh(x2))
                u = Kp * e + Ki * self.e_int[name] + Kd * de
            u = float(np.clip(u, -10, 10))

            dx1 = x2
            dx2 = -d * x2 - x1 + u
            x1 += dx1 * dt; x2 += dx2 * dt
            self.state[name] = [x1, x2]
            self.e_prev[name] = e

            th, yh = self.hist[name]
            th.append(self.t); yh.append(x1)
            if len(th) > 600:
                self.hist[name] = (th[-600:], yh[-600:])

            # settling time (5% band)
            if self.settling[name] is None and abs(x1 - sp) < 0.05*sp:
                # check stay
                if len(yh) > 30 and all(abs(y - sp) < 0.05*sp for y in yh[-30:]):
                    self.settling[name] = self.t

            # update plot
            th2, yh2 = self.hist[name]
            self.lines[name].set_data(th2, yh2)
            self.u_lines[name].set_data(th2, [u]*len(th2))

        if self.t > 10:
            self.t = 0
            for k in self.controllers:
                self.state[k] = [0.0, 0.0]
                self.e_int[k] = 0.0
                self.e_prev[k] = 0.0
                self.hist[k] = ([], [])
                self.settling[k] = None
            self.t_hist = []

        xmax = max(10, self.t)
        self.ax1.set_xlim(xmax - 10, xmax)
        self.ax2.set_xlim(xmax - 10, xmax)
        self.sp_line.set_ydata([sp, sp])
        self.canvas.draw_idle()
        self.update_scoreboard()

    def update_scoreboard(self):
        self.scoreboard.config(state=tk.NORMAL)
        self.scoreboard.delete("1.0", tk.END)
        self.scoreboard.insert(tk.END, f"{'Kontroler':<10} {'Settling':<10} {'y(now)':<8}\n")
        self.scoreboard.insert(tk.END, "-" * 32 + "\n")
        for name in self.controllers:
            st = self.settling[name]
            st_txt = f"{st:.2f}s" if st is not None else "--"
            y_now = self.state[name][0]
            self.scoreboard.insert(tk.END,
                f"{name:<10} {st_txt:<10} {y_now:+.3f}\n")
        self.scoreboard.config(state=tk.DISABLED)

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="⏸ Pause"); self.loop()
        else:
            self.btn.config(text="▶ Start")

    def loop(self):
        if not self.running: return
        for _ in range(2):
            self.step()
        self.after(int(self.dt_var.get() * 1000), self.loop)

        
# ============================================================
#  TAB 6.2: COMPARE ALL — 6 Kontroler, 1 Plant, Auto-Skor
# ============================================================

class CompareAllTab(ttk.Frame):
    """Bandingkan 6 kontroler pada plant identik + auto-scoring."""
    def __init__(self, master):
        super().__init__(master, padding=8)
        left = ttk.LabelFrame(self, text="Comparison Panel", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Label(left, text="6 Kontroler, 1 Plant",
                  font=("Arial", 13, "bold")).pack(pady=4)

        info = tk.Text(left, width=48, height=15, wrap=tk.WORD, font=("Arial", 9))
        info.pack()
        info.insert(tk.END, """TEORI — Benchmark Kontroler
Enam pendekatan diadu pada plant IDENTIK
    G(s) = 1/(s² + d·s + 1)
dengan damping d yang bisa diubah (simulasi
keausan plant / perubahan beban).

KONTROLER YANG DIUJI
  1. PID-Classic   — tuning Ziegler-Nichols
  2. PID-Overdamp  — lambat, sangat stabil
  3. PID-Aggr      — Kp besar, cepat tapi osilasi
  4. Fuzzy         — rule base 3x3 (Mamdani)
  5. Gain-Sched    — PID adaptif thd magnitudo error
  6. Fuzzy+PID     — hybrid: PID + trim fuzzy

METRIK PENILAIAN
  • IAE (∫|e|dt)          → kecil = baik
  • Overshoot (%)          → kecil = baik
  • Settling time (5% band)→ cepat = baik

SKOR AKHIR = 0.5·IAE_norm + 0.25·OS_norm + 0.25·Ts_norm
Kontroler dengan skor tertinggi diberi 🏆.

TAKEAWAY PENTING
Tidak ada kontroler yang selalu menang!
Ubahlah damping plant dan lihat peringkat berubah:
  • Plant enteng (d kecil) → PID-Aggr menang
  • Plant berat (d besar)  → Fuzzy/GS lebih adaptif
Pilih kontroler berdasarkan PRIORITAS aplikasi.""")
        info.config(state=tk.DISABLED)

        self.damp_var = tk.DoubleVar(value=2.0)
        self.noise_var = tk.DoubleVar(value=0.0)
        self.sp_var = tk.DoubleVar(value=1.0)

        for label, var, lo, hi, fmt in [
            ("Plant damping d", self.damp_var, 0.5, 4.0, "{:.2f}"),
            ("Sensor noise σ", self.noise_var, 0.0, 0.1, "{:.3f}"),
            ("Setpoint", self.sp_var, 0.5, 1.5, "{:.2f}"),
        ]:
            f = ttk.Frame(left); f.pack(fill=tk.X, pady=2)
            ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
            ttk.Scale(f, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL,
                      length=140).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=fmt.format(var.get()), width=6, font=("Courier", 9))
            lbl.pack(side=tk.LEFT)
            var.trace_add("write",
                lambda *a, v=var, l=lbl, f=fmt: (l.config(text=f.format(v.get())),
                                                 self.recompute()))

        row = ttk.Frame(left); row.pack(pady=8)
        ttk.Button(row, text="⟲ Recompute", command=self.recompute).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="🎲 Noise Run", command=self.noise_run).pack(side=tk.LEFT, padx=2)

        self.score_box = tk.Text(left, width=48, height=11,
                                 font=("Courier", 9), bg="#f0f8ff")
        self.score_box.pack(pady=6)

        right = ttk.Frame(self); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(9, 7), dpi=80)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.controllers = self._make_controllers()
        self.recompute()

    def _make_controllers(self):
        return {
            'PID-Classic':  {'color': '#2e86c1', 'type': 'pid',     'p': (3.8, 3.0, 3.2)},
            'PID-Overdamp': {'color': '#16a085', 'type': 'pid',     'p': (2.0, 1.0, 3.0)},
            'PID-Aggr':     {'color': '#c0392b', 'type': 'pid',     'p': (9.0, 4.0, 2.0)},
            'Fuzzy':        {'color': '#27ae60', 'type': 'fuzzy',   'p': None},
            'Gain-Sched':   {'color': '#e67e22', 'type': 'gainsch', 'p': (3.0, 2.0, 3.0)},
            'Fuzzy+PID':    {'color': '#8e44ad', 'type': 'fuzzpid', 'p': (3.0, 2.0, 3.0)},
        }

    def tri(self, x, a, b, c):
        y = 0.0
        if a <= x < b: y = (x - a) / (b - a) if b > a else 0
        elif b < x <= c: y = (c - x) / (c - b) if c > b else 0
        elif abs(x - b) < 1e-9: y = 1.0
        return float(np.clip(y, 0, 1))

    def fuzzy_u(self, e, de):
        def fz(x):
            return (self.tri(x, -1.2, -1.0, -0.2),
                    self.tri(x, -0.5, 0.0, 0.5),
                    self.tri(x, 0.2, 1.0, 1.2))
        eF = fz(e); dF = fz(de)
        eN, eZ, eP = eF; dN, dZ, dP = dF
        rules = [(eN,dN,-1.0),(eN,dZ,-1.0),(eN,dP,-0.5),
                 (eZ,dN,-1.0),(eZ,dZ,0.0),(eZ,dP,0.5),
                 (eP,dN,0.5),(eP,dZ,1.0),(eP,dP,1.0)]
        ws = vs = 0.0
        for we, wd, out in rules:
            w = min(we, wd); ws += w; vs += w * out
        return vs / ws if ws > 1e-9 else 0.0

    def simulate(self, cfg):
        d = self.damp_var.get(); sp = self.sp_var.get()
        noise = self.noise_var.get()
        dt = 0.02; T = 6.0
        steps = int(T / dt)
        x1 = x2 = 0.0
        e_int = 0.0; e_prev = 0.0
        iae = 0.0; peak = 0.0
        settle_t = None
        settle_check = []
        ts, ys = [], []

        for i in range(steps):
            e = sp - x1
            if noise > 0: e += np.random.randn() * noise
            e_int += e * dt
            de = (e - e_prev) / dt

            if cfg['type'] == 'pid':
                Kp, Ki, Kd = cfg['p']
                u = Kp * e + Ki * e_int + Kd * de
            elif cfg['type'] == 'fuzzy':
                u_n = self.fuzzy_u(np.clip(e / 0.5, -1.2, 1.2),
                                   np.clip(de / 2.0, -1.2, 1.2))
                u = u_n * 8.0
            elif cfg['type'] == 'gainsch':
                Kp, Ki, Kd = cfg['p']
                sched = 1.0 + 0.5 * np.tanh(abs(e) * 3)
                u = sched * (Kp * e + Ki * e_int + Kd * de)
            elif cfg['type'] == 'fuzzpid':
                Kp, Ki, Kd = cfg['p']
                u_pid = Kp * e + Ki * e_int + Kd * de
                u_trim = self.fuzzy_u(np.clip(e / 0.5, -1.2, 1.2),
                                      np.clip(de / 2.0, -1.2, 1.2)) * 2.0
                u = u_pid + u_trim
            else:
                u = 0.0

            u = float(np.clip(u, -12, 12))
            dx1 = x2
            dx2 = -d * x2 - x1 + u
            x1 += dx1 * dt; x2 += dx2 * dt
            iae += abs(e) * dt
            peak = max(peak, x1)

            if i > 50:
                settle_check.append(abs(x1 - sp))
                if len(settle_check) > 30: settle_check.pop(0)
                if settle_t is None and len(settle_check) == 30 and \
                   all(v < 0.05 * sp for v in settle_check):
                    settle_t = i * dt - 0.6

            ts.append(i * dt); ys.append(x1)
            e_prev = e

        overshoot = max(0.0, (peak - sp) / sp * 100)
        if settle_t is None: settle_t = T
        return np.array(ts), np.array(ys), iae, overshoot, settle_t

    def recompute(self):
        self.results = {}
        for name, cfg in self.controllers.items():
            ts, ys, iae, ov, st = self.simulate(cfg)
            self.results[name] = {'ts': ts, 'ys': ys, 'iae': iae,
                                  'overshoot': ov, 'settle': st}
        self.draw()
        self.update_score()

    def noise_run(self):
        self.noise_var.set(0.03)
        self.recompute()

    def update_score(self):
        names = list(self.controllers.keys())
        iaes = np.array([self.results[n]['iae'] for n in names])
        ovs = np.array([self.results[n]['overshoot'] for n in names])
        sts = np.array([self.results[n]['settle'] for n in names])

        def norm_inv(x):
            r = x.max() - x.min()
            return 1 - (x - x.min()) / r if r > 1e-9 else np.ones_like(x)

        scores = 0.5 * norm_inv(iaes) + 0.25 * norm_inv(ovs) + 0.25 * norm_inv(sts)
        rows = [(names[i], iaes[i], ovs[i], sts[i], scores[i])
                for i in range(len(names))]
        rows.sort(key=lambda r: -r[4])

        self.score_box.config(state=tk.NORMAL)
        self.score_box.delete("1.0", tk.END)
        self.score_box.insert(tk.END,
            f"{'Kontroler':<14}{'IAE':>7}{'OS%':>7}{'Ts':>7}{'Skor':>8}\n")
        self.score_box.insert(tk.END, "-" * 46 + "\n")
        for i, (n, iae, ov, st, sc) in enumerate(rows):
            mark = "🏆" if i == 0 else "  "
            self.score_box.insert(tk.END,
                f"{mark}{n:<11}{iae:>7.3f}{ov:>7.1f}{st:>7.2f}{sc:>8.3f}\n")
        self.score_box.config(state=tk.DISABLED)

    def draw(self):
        self.ax1.clear(); self.ax2.clear()
        for name, cfg in self.controllers.items():
            r = self.results[name]
            self.ax1.plot(r['ts'], r['ys'], color=cfg['color'], lw=1.9, label=name)
        self.ax1.axhline(self.sp_var.get(), color='k', ls='--', lw=1.2, label='SP')
        self.ax1.set_ylim(-0.3, max(1.8, self.sp_var.get() * 1.6))
        self.ax1.set_xlabel("Waktu (s)"); self.ax1.set_ylabel("Output")
        self.ax1.set_title(f"Step Response — 6 Kontroler "
                           f"(damping = {self.damp_var.get():.2f})")
        self.ax1.grid(alpha=0.3)
        self.ax1.legend(loc='lower right', fontsize=7, ncol=2)

        names = list(self.controllers.keys())
        iaes = [self.results[n]['iae'] for n in names]
        colors = [self.controllers[n]['color'] for n in names]
        bars = self.ax2.barh(names, iaes, color=colors, alpha=0.85)
        # Annotate values
        for bar, v in zip(bars, iaes):
            self.ax2.text(v + max(iaes)*0.01, bar.get_y() + bar.get_height()/2,
                          f'{v:.3f}', va='center', fontsize=8)
        self.ax2.set_xlabel("IAE (kecil = baik)")
        self.ax2.set_title("Integral Absolute Error")
        self.ax2.grid(alpha=0.3, axis='x')
        self.canvas.draw_idle()

# ============================================================
#  TAB 7: TUGAS
# ============================================================
# ============================================================
#  TAB TUGAS (updated — 9 tugas mencakup semua tab)
# ============================================================
class TugasTab(ttk.Frame):
    TUGAS = [
        ("T1 — Fuzzy Dasar & Rule Base",
         "TAB: 🧠 Fuzzy  +  🔥 Fuzzy Heatmap\n\n"
         "1) Buka tab 'Fuzzy'. Atur setpoint 60°C, tunggu stabil.\n"
         "   Catat: waktu settling, overshoot, error steady-state.\n"
         "2) Aktifkan disturbance +2 heat/s. Amati recovery.\n"
         "3) Aktifkan sensor noise σ=1.5. Apa yang terjadi?\n"
         "4) Buka tab 'Fuzzy Heatmap'. Set e=0.5, Δe=0.\n"
         "   Rule mana yang menyala? Berapa bobotnya?\n"
         "5) Geser e=-0.5, Δe=+0.5 (error minus tapi membaik).\n"
         "   Mengapa rule (NB, PB) menghasilkan u negatif sedang\n"
         "   (NS)? Jelaskan logika fisikanya.\n\n"
         "REFLEKSI: Mengapa fuzzy TIDAK PERNAH hanya 1 rule\n"
         "aktif? Apa implikasinya terhadap kehalusan output?"),

        ("T2 — NN Dasar & Neuron Flow",
         "TAB: 🤖 NN  +  🧠 NN Flow\n\n"
         "1) Tab 'NN': set hidden=5, LR=0.1, noise=0.15.\n"
         "   Amati loss curve. Apakah underfit/overfit?\n"
         "2) Ubah hidden=25. Bagaimana hasilnya?\n"
         "3) Buka 'NN Flow'. Set input x=-3, 0, +3.\n"
         "   Node hidden mana yang menyala untuk tiap x?\n"
         "   Apakah node yang sama? Mengapa?\n"
         "4) Klik 'Train 300x'. Amati perubahan warna\n"
         "   (merah=positif, biru=negatif) dan ketebalan garis.\n"
         "5) Setelah training, apakah koneksi input→hidden\n"
         "   lebih 'sparse' (banyak garis tipis) atau sebaliknya?\n\n"
         "REFLEKSI: Setiap node hidden cenderung 'mengkode'\n"
         "segmen x tertentu. Hubungkan dengan konsep\n"
         "'distributed representation' di NN."),

        ("T3 — GA Landscape & Evolusi",
         "TAB: 🧬 GA  +  🗺 GA Landscape  +  🌐 PSO 3D\n\n"
         "1) Tab 'GA Landscape'. Klik 'Evolve' 30 generasi.\n"
         "   Screenshot: bagaimana populasi bergerak?\n"
         "2) Screenshot crossover event (garis oranye +\n"
         "   anak ✗ merah). Berapa lama muncul?\n"
         "3) Set mutation rate = 0.05. Jalankan 30 generasi.\n"
         "   Apakah populasi konvergen prematur?\n"
         "4) Set mutation = 0.9. Apa yang terjadi?\n"
         "5) Bandingkan dengan 'PSO 3D' (trail gbest).\n"
         "   Mana yang lebih stabil? Mana yang lebih cepat?\n\n"
         "REFLEKSI: Tuliskan trade-off antara eksplorasi\n"
         "(mutasi tinggi) dan eksploitasi (mutasi rendah)\n"
         "dengan data yang Anda amati."),

        ("T4 — ANFIS: Belajar dari Data",
         "TAB: 🌀 ANFIS  +  📊 ANFIS Evolution\n\n"
         "1) Tab 'ANFIS Evolution'. Set N_MF=5, LR=0.05.\n"
         "2) Klik 'Train' sebentar, Pause di sekitar epoch 100,\n"
         "   500, 1500. Screenshot tiap MF set.\n"
         "3) Bandingkan: MF mana yang 'berevolusi' paling\n"
         "   banyak? (tepi atau tengah?)\n"
         "4) Ulangi dengan N_MF=8. Apakah hasilnya lebih baik?\n"
         "   Apakah jumlah parameter lebih banyak selalu\n"
         "   menguntungkan?\n"
         "5) Diskusikan: bagaimana ANFIS berbeda dari tab\n"
         "   'NN' (murni black-box)? Apa yang membuat ANFIS\n"
         "   lebih 'interpretable'?\n\n"
         "REFLEKSI: Dalam industri, kapan Anda pilih ANFIS\n"
         "vs NN biasa? Kaitkan dengan regulasi & kebutuhan\n"
         "audit yang sering muncul di manufaktur."),

        ("T5 — RL & Animasi Pendulum",
         "TAB: 🎮 RL  +  🕹 Pendulum\n\n"
         "A. RL Q-Learning\n"
         "1) Train 500 episode. Perhatikan reward curve.\n"
         "2) Klik 'Test Policy'. Berapa lama tongkat tegak?\n"
         "3) Ubah max torque τ=2.0. Apakah agent tetap belajar?\n\n"
         "B. Pendulum PID\n"
         "4) Buka 'Pendulum'. Set Kp=100, Ki=20, Kd=2.\n"
         "   Klik 'Start'. Amati osilasi.\n"
         "5) Naikkan Kd=15. Apa efeknya? Mengapa?\n"
         "6) Aktifkan noise σ=0.1. Apakah tongkat masih tegak?\n"
         "7) Klik 'Push!' — simulasi gangguan. Bagaimana\n"
         "   PID merespons? Bandingkan dengan RL.\n\n"
         "REFLEKSI: RL belajar 'dari nol' tanpa model plant.\n"
         "PID butuh model. Sebutkan 3 kelebihan & 3 kelemahan\n"
         "masing-masing untuk aplikasi industri nyata."),

        ("T6 — Fuzzy Surface & Analisis",
         "TAB: 📐 Fuzzy Surface\n\n"
         "1) Buka 'Fuzzy Surface'. Amati permukaan kontrol.\n"
         "   Apakah mulus? Mengapa?\n"
         "2) Gerakkan titik merah ke (e=+1.2, Δe=0).\n"
         "   Berapa output u? Apakah masuk akal?\n"
         "3) Ke (e=0, Δe=-1.2)? Berapa u?\n"
         "4) Diskusikan: titik mana yang menghasilkan u=0%?\n"
         "   Apakah 'diam' hanya saat e=0 & Δe=0?\n"
         "5) Snapshot PNG permukaan → lampirkan ke laporan.\n\n"
         "REFLEKSI: Kaitkan bentuk permukaan dengan rule base.\n"
         "Jika kita ganti rule (PB, PB) → 'NS' (bukan PB),\n"
         "prediksikan bentuk permukaan yang baru."),

        ("T7 — Step Race: Benchmark Kontroler",
         "TAB: 🏁 Step Race  +  🥇 Compare All\n\n"
         "1) Tab 'Step Race'. Start. Biarkan ~10s.\n"
         "   Catat settling time tiap kontroler.\n"
         "2) Ubah damping = 3.5. Reset. Ulangi.\n"
         "   Apakah pemenang berubah?\n"
         "3) Buka 'Compare All'. Catat skor 6 kontroler.\n"
         "4) Ubah plant damping: 1.0, 2.0, 3.5.\n"
         "   Isi tabel: [damping × kontroler] → rank.\n"
         "5) Tambahkan sensor noise σ=0.03. Siapa yang paling\n"
         "   robust? Siapa yang paling 'gugup'?\n\n"
         "REFLEKSI: Simpulkan — apakah ada kontroler yang\n"
         "SELALU menang? Kaitkan dengan 'No Free Lunch\n"
         "Theorem' dalam optimasi & kontrol."),

        ("T8 — PSO 3D & Ruang Pencarian",
         "TAB: 🐝 PSO  +  🌐 PSO 3D\n\n"
         "1) Tab 'PSO 3D'. Start dengan w=0.7.\n"
         "2) Drag mouse untuk melihat dari sudut berbeda.\n"
         "   Screenshot: posisi swarm di iter 20, 60, 120.\n"
         "3) Ubah w=0.1 (partikel 'berat'). Apa yang berubah?\n"
         "   Berapa iterasi untuk konvergen?\n"
         "4) Ubah w=0.95. Apakah partikel 'kabur' dari solusi?\n"
         "5) Klik '➕ Particle' saat running — apa efeknya\n"
         "   pada trail gbest?\n"
         "6) Diskusikan: mengapa c1 & c2 mempengaruhi\n"
         "   eksplorasi vs eksploitasi?\n\n"
         "REFLEKSI: Ruang (Kp,Ki,Kd) adalah 3D. Bayangkan\n"
         "untuk kontroler dengan 10 parameter. Bagaimana\n"
         "visualisasi & kompleksitasnya berubah?"),

        ("T9 — Integrasi: Pilih Kontroler untuk Industri",
         "TAB: SEMUA (analisis akhir)\n\n"
         "Skenario: Anda diminta memilih kontroler untuk oven\n"
         "industri yang SUHU-nya harus 250°C ± 2°C.\n\n"
         "Bandingkan 6 kontroler (Compare All) pada:\n"
         "  a) Startup dingin (setpoint 25→250°C)\n"
         "  b) Disturbance: pintu oven dibuka 5 detik\n"
         "  c) Sensor noisy (termokopel murah)\n"
         "  d) Plant berubah karena usia (damping naik)\n\n"
         "Untuk setiap skenario, pilih kontroler + alasan.\n"
         "Gunakan data IAE, overshoot, settling dari\n"
         "tab Compare All sebagai bukti.\n\n"
         "REFLEKSI AKHIR (1 halaman):\n"
         "  • Kontroler mana yang Anda rekomendasikan?\n"
         "  • Kapan fuzzy lebih baik dari PID?\n"
         "  • Kapan GA/PSO diperlukan?\n"
         "  • Apa risiko black-box (NN/RL) di industri\n"
         "    yang diaudit?"),
    ]

    def __init__(self, master):
        super().__init__(master, padding=8)

        header = ttk.Frame(self); header.pack(fill=tk.X, pady=4)
        ttk.Label(header, text="📝  Tugas Praktikum — Sistem Kendali Cerdas",
                  font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Label(header,
                  text="(9 tugas · jawab sambil eksplor tab simulasi · simpan .txt)",
                  foreground="gray").pack(side=tk.LEFT, padx=8)

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        self.answers = {}
        for title, content in self.TUGAS:
            frame = ttk.Frame(nb, padding=6)
            nb.add(frame, text=title.split('—')[0].strip())

            # Split pane: instruksi (atas) vs jawaban (bawah)
            pane = ttk.PanedWindow(frame, orient=tk.VERTICAL)
            pane.pack(fill=tk.BOTH, expand=True)

            top = ttk.LabelFrame(pane, text=title, padding=6)
            inst = tk.Text(top, wrap=tk.WORD, height=12,
                           font=("Courier", 10), bg="#f8f9fa",
                           foreground="#1a3a5c")
            inst.pack(fill=tk.BOTH, expand=True)
            inst.insert(tk.END, content)
            inst.config(state=tk.DISABLED)
            pane.add(top, weight=1)

            bot = ttk.LabelFrame(pane, text="Jawaban Anda", padding=6)
            txt = scrolledtext.ScrolledText(bot, wrap=tk.WORD,
                                            font=("Courier", 10))
            txt.pack(fill=tk.BOTH, expand=True)
            pane.add(bot, weight=2)

            self.answers[title] = txt

        bar = ttk.Frame(self); bar.pack(fill=tk.X, pady=6)
        ttk.Button(bar, text="💾 Simpan Semua Jawaban",
                   command=self.save_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="📂 Muat Jawaban",
                   command=self.load_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="🗑 Bersihkan",
                   command=self.clear_all).pack(side=tk.LEFT, padx=4)

        # Progress indicator
        self.progress_lbl = ttk.Label(bar, text="Progress: 0/9 terisi",
                                      font=("Arial", 10, "bold"),
                                      foreground="navy")
        self.progress_lbl.pack(side=tk.RIGHT, padx=10)
        self.progress_bar = ttk.Progressbar(bar, length=180, maximum=len(self.TUGAS))
        self.progress_bar.pack(side=tk.RIGHT, padx=6)

        # Update progress on typing
        for txt in self.answers.values():
            txt.bind("<KeyRelease>", lambda e: self.update_progress())
        self.update_progress()

    def update_progress(self):
        n = sum(1 for txt in self.answers.values()
                if len(txt.get("1.0", tk.END).strip()) > 30)
        self.progress_lbl.config(text=f"Progress: {n}/{len(self.TUGAS)} terisi")
        self.progress_bar['value'] = n

    def save_all(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"jawaban_tugas_{datetime.now():%Y%m%d_%H%M}.txt",
            filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Jawaban Tugas Sistem Kendali Cerdas\n")
                f.write(f"Disimpan: {datetime.now():%Y-%m-%d %H:%M}\n")
                f.write("=" * 66 + "\n\n")
                for title, txt in self.answers.items():
                    jawaban = txt.get("1.0", tk.END).strip()
                    f.write(f"\n### {title}\n")
                    f.write("-" * 66 + "\n")
                    f.write((jawaban if jawaban else "(belum diisi)") + "\n")
            messagebox.showinfo("OK", f"Tersimpan:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_all(self):
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            sections = content.split("### ")
            for i, (title, _) in enumerate(self.TUGAS):
                if i + 1 < len(sections):
                    body = sections[i + 1]
                    idx = body.find("-" * 66)
                    if idx >= 0:
                        body = body[idx + 66:].strip()
                    self.answers[title].delete("1.0", tk.END)
                    self.answers[title].insert("1.0", body)
            self.update_progress()
            messagebox.showinfo("OK", "Jawaban berhasil dimuat.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def clear_all(self):
        if not messagebox.askyesno("Konfirmasi",
                                    "Hapus semua jawaban?"):
            return
        for txt in self.answers.values():
            txt.delete("1.0", tk.END)
        self.update_progress()
        

# ============================================================
#  TAB KUIS (updated — 20 soal, kategori & feedback)
# ============================================================
class QuizTab(ttk.Frame):
    QUESTIONS = [
        # ---------- FUZZY ----------
        {"cat": "Fuzzy",
         "q": "Keunggulan utama Fuzzy Logic vs PID klasik adalah...",
         "opts": ["Selalu lebih cepat settling",
                  "Tidak butuh model eksak & mudah diinterpretasi pakar",
                  "Konsumsi daya lebih kecil",
                  "Tidak perlu tuning sama sekali"],
         "ans": 1,
         "exp": "Fuzzy dirancang dari pengetahuan pakar (IF-THEN), bukan "
                "dari model matematis plant. Cocok saat plant sulit dimodelkan."},

        {"cat": "Fuzzy",
         "q": "Pada rule base fuzzy 3×3, mengapa pada praktiknya SELALU "
              "lebih dari 1 rule yang aktif?",
         "opts": ["Karena bug software",
                  "Karena MF bertumpang-tindih → μ>0 di banyak rule sekaligus",
                  "Karena 9 rule dieksekusi bersamaan sebagai hukuman",
                  "Karena defuzzifikasi butuh minimal 3 rule"],
         "ans": 1,
         "exp": "Membership function segitiga/gaussian saling overlap, "
                "sehingga satu nilai e bisa memiliki μ>0 untuk NB, Z, dan PB "
                "sekaligus. Ini yang membuat output fuzzy HALUS."},

        {"cat": "Fuzzy",
         "q": "Pada defuzzifikasi centroid Mamdani, hasil akhir adalah...",
         "opts": ["Median output",
                  "Nilai maksimum dari rule terkuat",
                  "Rata-rata terbobot: Σ(wᵢ·uᵢ)/Σwᵢ",
                  "Random dari 9 rule"],
         "ans": 2,
         "exp": "Centroid = weighted average. Setiap rule menyumbang "
                "berdasarkan kekuatannya (w = min μ_e, μ_Δe)."},

        # ---------- NN ----------
        {"cat": "NN",
         "q": "Pada tab 'NN Flow', warna merah pada koneksi berarti...",
         "opts": ["Bobot negatif (menghambat)",
                  "Bobot positif (memperkuat sinyal)",
                  "Error besar",
                  "Neuron mati"],
         "ans": 1,
         "exp": "Konvensi visual: merah = w>0 (excitatory), biru = w<0 "
                "(inhibitory). Ketebalan garis = |w|."},

        {"cat": "NN",
         "q": "Setelah training NN dengan hidden=10, neuron hidden "
              "cenderung...",
         "opts": ["Semua menyala identik untuk setiap x",
                  "Mengkode segmen/karakteristik berbeda dari input",
                  "Menjadi nol semua",
                  "Menjadi random"],
         "ans": 1,
         "exp": "Fenomena 'distributed representation'. Node berbeda "
                "spesialis pada area input berbeda — ini dasar NN belajar "
                "fungsi kompleks."},

        {"cat": "NN",
         "q": "Learning rate terlalu besar (mis. 0.5) menyebabkan...",
         "opts": ["Training tidak konvergen / loss naik-turun",
                  "Training selalu sukses lebih cepat",
                  "Bobot menjadi nol",
                  "Tidak ada efek"],
         "ans": 0,
         "exp": "Langkah update terlalu jauh → melewati minimum. Loss "
                "berosilasi atau divergen. Gunakan LR kecil + decay."},

        # ---------- ANFIS ----------
        {"cat": "ANFIS",
         "q": "ANFIS = kombinasi...",
         "opts": ["GA + PSO",
                  "Fuzzy + Neural Network",
                  "RL + PID",
                  "SVM + GA"],
         "ans": 1,
         "exp": "Adaptive Neuro-Fuzzy Inference System. Struktur fuzzy "
                "(rule + MF) tapi parameter (c, σ, koefisien Sugeno) "
                "dilatih dengan gradient descent."},

        {"cat": "ANFIS",
         "q": "Pada tab 'ANFIS Evolution', MF yang bergeser & melebar "
              "menunjukkan...",
         "opts": ["Kerusakan data",
                  "Parameter premis (c, σ) dioptimasi dari data",
                  "MF dibuat manual oleh pakar",
                  "Fuzzy tidak bekerja"],
         "ans": 1,
         "exp": "Inilah kekuatan ANFIS: MF tidak perlu ditentukan pakar — "
                "sistem belajar posisi & lebar MF optimal dari data historis."},

        {"cat": "ANFIS",
         "q": "Kapan ANFIS LEBIH disukai daripada NN murni di industri?",
         "opts": ["Saat butuh kecepatan ekstrem",
                  "Saat butuh interpretabilitas & audit trail (regulasi)",
                  "Saat data sangat sedikit",
                  "Saat tidak ada waktu training"],
         "ans": 1,
         "exp": "Di industri teregulasi (farmasi, makanan, otomotif), "
                "auditor butuh penjelasan 'mengapa' keputusan diambil. "
                "ANFIS menyediakan MF & rule yang bisa dibaca manusia."},

        # ---------- GA ----------
        {"cat": "GA",
         "q": "Pada tab 'GA Landscape', individu yang di-mutasi "
              "ditandai dengan...",
         "opts": ["Tanda ✗ merah",
                  "Tanda ✗ ungu",
                  "Bintang emas",
                  "Garis oranye"],
         "ans": 1,
         "exp": "Ungu = anak yang ditambahkan noise Gaussian (mutasi). "
                "Merah = anak dari crossover saja (tanpa mutasi). "
                "Emas = individu terbaik."},

        {"cat": "GA",
         "q": "Mutation rate = 0.05 (sangat rendah) menyebabkan...",
         "opts": ["Konvergensi sangat cepat tapi mudah premature",
                  "Populasi tidak pernah konvergen",
                  "GA tidak bisa jalan",
                  "Fitness naik terus"],
         "ans": 0,
         "exp": "Eksplorasi kurang → populasi mengerumun di solusi lokal. "
                "Trade-off klasik eksplorasi vs eksploitasi."},

        {"cat": "GA",
         "q": "Operator yang mencegah konvergensi prematur adalah...",
         "opts": ["Seleksi", "Crossover", "Mutasi", "Elitisme"],
         "ans": 2,
         "exp": "Mutasi menambah keragaman genetik dan mendorong pencarian "
                "di area baru ruang solusi."},

        # ---------- PSO ----------
        {"cat": "PSO",
         "q": "Parameter 'w' (inertia) BESAR pada PSO menyebabkan...",
         "opts": ["Konvergensi cepat tapi mudah terjebak lokal",
                  "Eksplorasi global kuat, konvergensi bisa lambat",
                  "Partikel berhenti",
                  "Tidak ada pengaruh"],
         "ans": 1,
         "exp": "w besar = momentum dipertahankan → partikel 'melayang' "
                "jauh. w kecil = partikel cepat 'ditarik' ke pbest/gbest."},

        {"cat": "PSO",
         "q": "Pada 'PSO 3D', sumbu (Kp, Ki, Kd) merepresentasikan...",
         "opts": ["Waktu, frekuensi, amplitudo",
                  "Gain proportional, integral, derivative kontroler",
                  "State RL",
                  "Layer NN"],
         "ans": 1,
         "exp": "Setiap partikel adalah kandidat PID. PSO mencari titik "
                "(Kp,Ki,Kd) optimal untuk meminimalkan IAE."},

        # ---------- RL ----------
        {"cat": "RL",
         "q": "Q(s,a) pada Q-Learning merepresentasikan...",
         "opts": ["Reward seketika saja",
                  "Expected discounted return jika aksi a diambil dari state s",
                  "Probabilitas transisi",
                  "Fungsi biaya"],
         "ans": 1,
         "exp": "Q(s,a) ≈ Σ γᵏ·r. Setelah konvergen, policy optimal = "
                "argmax_a Q(s,a)."},

        {"cat": "RL",
         "q": "Trade-off ε-greedy pada RL adalah...",
         "opts": ["Akurasi vs kecepatan",
                  "Eksplorasi (ε besar) vs eksploitasi (ε kecil)",
                  "Memori vs CPU",
                  "Tidak ada trade-off"],
         "ans": 1,
         "exp": "Di awal training ε=1 (explore banyak). Seiring belajar, "
                "ε menurun → agent memanfaatkan pengetahuan (exploit)."},

        {"cat": "RL",
         "q": "Keunggulan RL dibanding PID untuk kontrol adalah...",
         "opts": ["Selalu lebih cepat",
                  "Belajar policy optimal tanpa model plant eksak",
                  "Butuh GPU selalu",
                  "Tidak butuh reward"],
         "ans": 1,
         "exp": "RL = model-free. Cocok untuk plant kompleks yang sulit "
                "dimodelkan, tapi butuh banyak data / simulasi."},

        # ---------- BENCHMARK ----------
        {"cat": "Benchmark",
         "q": "Pada 'Compare All' dengan damping plant berubah, mengapa "
              "peringkat kontroler bisa berubah?",
         "opts": ["Bug software",
                  "Karena tiap kontroler punya asumsi & karakter berbeda "
                  "(No Free Lunch Theorem)",
                  "Karena random",
                  "Karena noise sensor"],
         "ans": 1,
         "exp": "No Free Lunch: tidak ada algoritma yang unggul di SEMUA "
                "masalah. Kontroler harus dipilih sesuai karakter plant & "
                "prioritas aplikasi."},

        {"cat": "Benchmark",
         "q": "Kontroler PID dengan Kp terlalu besar cenderung...",
         "opts": ["Lambat & overdamped",
                  "Osilasi / overshoot besar",
                  "Tidak merespons sama sekali",
                  "Error steady-state besar"],
         "ans": 1,
         "exp": "Kp besar = gain loop tinggi → sistem mendekati batas "
                "stabilitas → osilasi. Perlu Ki kecil & Kd untuk meredam."},

        {"cat": "Benchmark",
         "q": "Untuk oven industri dengan sensor termokopel murah "
              "(noisy), kontroler PALING tepat adalah...",
         "opts": ["PID-Aggr (Kp tinggi)",
                  "Fuzzy atau Fuzzy+PID (filter alami dari overlap MF)",
                  "Open-loop",
                  "On-off sederhana"],
         "ans": 1,
         "exp": "Fuzzy secara alami 'smooth' input noisy karena banyak "
                "rule rata-rata outputnya. PID turunan (D) justru "
                "memperkuat noise."},
    ]

    def __init__(self, master):
        super().__init__(master, padding=8)

        header = ttk.Frame(self); header.pack(fill=tk.X)
        ttk.Label(header, text="❓ Kuis Interaktif — Sistem Kendali Cerdas",
                  font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text=f"({len(self.QUESTIONS)} soal PG · kategori "
                               f"Fuzzy / NN / ANFIS / GA / PSO / RL / Benchmark)",
                  foreground="gray").pack(side=tk.LEFT, padx=10)

        # Filter & shuffle bar
        ctrl = ttk.Frame(self); ctrl.pack(fill=tk.X, pady=4)
        ttk.Label(ctrl, text="Filter kategori:").pack(side=tk.LEFT, padx=4)
        self.cat_var = tk.StringVar(value="Semua")
        cats = ["Semua"] + sorted(set(q["cat"] for q in self.QUESTIONS))
        cb = ttk.Combobox(ctrl, textvariable=self.cat_var, values=cats,
                          state="readonly", width=14)
        cb.pack(side=tk.LEFT)
        cb.bind("<<ComboboxSelected>>", lambda e: self.rebuild())

        ttk.Button(ctrl, text="🔀 Acak Urutan",
                   command=self.shuffle).pack(side=tk.LEFT, padx=6)
        self.shuffle_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Sembunyikan pembahasan sampai diperiksa",
                        variable=self.shuffle_mode).pack(side=tk.LEFT, padx=6)

        # Scrollable content
        container = ttk.Frame(self); container.pack(fill=tk.BOTH, expand=True, pady=6)
        canvas = tk.Canvas(container, highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scroll = ttk.Frame(canvas)
        self.scroll.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.vars = []
        self.exp_labels = []
        self._order = list(range(len(self.QUESTIONS)))

        # Footer bar
        bar = ttk.Frame(self); bar.pack(fill=tk.X, pady=4)
        ttk.Button(bar, text="✔ Periksa Jawaban",
                   command=self.check).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="⟲ Ulangi",
                   command=self.clear).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="⤓ Hasil CSV",
                   command=self.export).pack(side=tk.LEFT, padx=4)

        self.score_lbl = ttk.Label(bar, text="Skor: --",
                                   font=("Arial", 12, "bold"), foreground="navy")
        self.score_lbl.pack(side=tk.LEFT, padx=20)
        self.pbar = ttk.Progressbar(bar, length=220, maximum=100)
        self.pbar.pack(side=tk.LEFT, padx=6)
        self.grade_lbl = ttk.Label(bar, text="", font=("Arial", 11, "bold"))
        self.grade_lbl.pack(side=tk.LEFT, padx=10)

        self.rebuild()

    # --- build/filter UI ---
    def rebuild(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self.vars.clear(); self.exp_labels.clear()

        cat = self.cat_var.get()
        self._order = [i for i in self._order
                       if cat == "Semua" or self.QUESTIONS[i]["cat"] == cat]

        for n, qi in enumerate(self._order):
            q = self.QUESTIONS[qi]
            box = ttk.LabelFrame(self.scroll,
                                 text=f"Soal {n+1}  [{q['cat']}]", padding=8)
            box.pack(fill=tk.X, pady=4, padx=4)
            ttk.Label(box, text=q["q"], font=("Arial", 10, "bold"),
                      wraplength=880, justify="left").pack(anchor="w", pady=2)
            var = tk.IntVar(value=-1)
            for j, opt in enumerate(q["opts"]):
                ttk.Radiobutton(box, text=f"{chr(65+j)}. {opt}",
                                variable=var, value=j).pack(anchor="w")
            self.vars.append(var)
            exp = ttk.Label(box, text="", foreground="darkgreen",
                            font=("Arial", 9, "italic"), wraplength=880)
            exp.pack(anchor="w", pady=2)
            self.exp_labels.append(exp)

    def shuffle(self):
        import random
        random.shuffle(self._order)
        self.rebuild()
        self.clear_score()

    def check(self):
        score = 0
        for i, qi in enumerate(self._order):
            q = self.QUESTIONS[qi]
            v = self.vars[i].get()
            lbl = self.exp_labels[i]
            if v == q["ans"]:
                score += 1
                lbl.config(text=f"✔ Benar. {q['exp']}", foreground="green")
            else:
                correct = chr(65 + q["ans"])
                lbl.config(text=f"✘ Salah. Jawaban: {correct}. {q['exp']}",
                           foreground="red")
        total = len(self._order)
        pct = score / total * 100 if total else 0
        self.score_lbl.config(text=f"Skor: {score}/{total} ({pct:.0f}%)")
        self.pbar['value'] = pct
        if pct >= 85:   grade, color = "🏆 Excellent!", "#27ae60"
        elif pct >= 70: grade, color = "👍 Baik", "#2e86c1"
        elif pct >= 50: grade, color = "⚠ Cukup — baca teori lagi", "#e67e22"
        else:           grade, color = "❌ Perlu review materi", "#c0392b"
        self.grade_lbl.config(text=grade, foreground=color)

    def clear_score(self):
        self.score_lbl.config(text="Skor: --")
        self.pbar['value'] = 0
        self.grade_lbl.config(text="")

    def clear(self):
        for i in range(len(self.vars)):
            self.vars[i].set(-1)
            self.exp_labels[i].config(text="")
        self.clear_score()

    def export(self):
        rows = []
        for i, qi in enumerate(self._order):
            q = self.QUESTIONS[qi]
            picked = self.vars[i].get()
            picked_txt = chr(65 + picked) if picked >= 0 else "-"
            correct_txt = chr(65 + q["ans"])
            rows.append((q["cat"], q["q"][:80],
                         picked_txt, correct_txt,
                         "BENAR" if picked == q["ans"] else "SALAH"))
        export_csv(self, ["kategori", "soal", "jawaban_anda",
                          "jawaban_benar", "status"], rows,
                   f"kuis_hasil_{datetime.now():%Y%m%d_%H%M}.csv")

# ============================================================
#  MAIN APP
# ============================================================
class App:
    def __init__(self, root):
        root.title("Media Pembelajaran Interaktif — Sistem Kendali Cerdas")
        root.geometry("1400x880")

        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("TNotebook.Tab", padding=[11, 7], font=("Arial", 10, "bold"))

        nb = ttk.Notebook(root)
        nb.pack(fill=tk.BOTH, expand=True)

        # --- tab dasar ---
        nb.add(FuzzyTab(nb),   text=" 🧠 Fuzzy ")
        nb.add(NNTab(nb),      text=" 🤖 NN ")
        nb.add(GATab(nb),      text=" 🧬 GA ")
        nb.add(ANFISTab(nb),   text=" 🌀 ANFIS ")
        nb.add(PSOTab(nb),     text=" 🐝 PSO ")
        nb.add(RLTab(nb),      text=" 🎮 RL ")

        # --- tab visual lanjutan ---
        nb.add(PSO3DTab(nb),         text=" 🌐 PSO 3D ")
        nb.add(PendulumTab(nb),      text=" 🕹 Pendulum ")
        nb.add(FuzzySurfaceTab(nb),  text=" 📐 Fuzzy Surface ")
        nb.add(StepRaceTab(nb),      text=" 🏁 Step Race ")

        # --- tab visual teori-mendalam (BARU) ---
        nb.add(NNFlowTab(nb),         text=" 🧠 NN Flow ")
        nb.add(GALandscapeTab(nb),    text=" 🗺 GA Landscape ")
        nb.add(FuzzyHeatmapTab(nb),   text=" 🔥 Fuzzy Heatmap ")
        nb.add(ANFISEvolutionTab(nb), text=" 📊 ANFIS Evolution ")
        nb.add(CompareAllTab(nb),     text=" 🥇 Compare All ")

        # --- tugas & kuis ---
        nb.add(TugasTab(nb), text=" 📝 Tugas ")
        nb.add(QuizTab(nb),  text=" ❓ Kuis ")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
