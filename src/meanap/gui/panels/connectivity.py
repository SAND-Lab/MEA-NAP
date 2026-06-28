"""Functional connectivity & thresholding settings panel."""

from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLineEdit, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from meanap.params import Params


class ConnectivityPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── STTC / lag ────────────────────────────────────────────────────────
        sttc_box = QGroupBox("Spike time tiling coefficient (STTC)")
        form = QFormLayout(sttc_box)

        self.lag_vals = QLineEdit("10, 15, 25")
        self.lag_vals.setPlaceholderText("Comma-separated lag values in ms")

        self.trunc_rec = QCheckBox()
        self.trunc_length = QDoubleSpinBox()
        self.trunc_length.setRange(1, 100000)
        self.trunc_length.setDecimals(0)
        self.trunc_length.setSuffix(" s")
        self.trunc_length.setValue(120)

        form.addRow("Lag values (ms)", self.lag_vals)
        form.addRow("Truncate recording", self.trunc_rec)
        form.addRow("Truncation length", self.trunc_length)

        # ── Adjacency matrix ──────────────────────────────────────────────────
        adj_box = QGroupBox("Adjacency matrix")
        adj_layout = QHBoxLayout(adj_box)

        self._adj_group = QButtonGroup(self)
        self.weighted_btn = QRadioButton("Weighted")
        self.binary_btn = QRadioButton("Binary")
        self.weighted_btn.setChecked(True)
        self._adj_group.addButton(self.weighted_btn)
        self._adj_group.addButton(self.binary_btn)

        adj_layout.addWidget(self.weighted_btn)
        adj_layout.addWidget(self.binary_btn)
        adj_layout.addStretch()

        # ── Probabilistic thresholding ────────────────────────────────────────
        thr_box = QGroupBox("Probabilistic thresholding")
        form2 = QFormLayout(thr_box)

        self.prob_thresh_rep_num = QSpinBox()
        self.prob_thresh_rep_num.setRange(10, 10000)
        self.prob_thresh_rep_num.setValue(200)

        self.prob_thresh_tail = QDoubleSpinBox()
        self.prob_thresh_tail.setRange(0.001, 0.5)
        self.prob_thresh_tail.setDecimals(3)
        self.prob_thresh_tail.setSingleStep(0.005)
        self.prob_thresh_tail.setValue(0.05)

        self.prob_thresh_plot_checks = QCheckBox()
        self.prob_thresh_plot_checks_n = QSpinBox()
        self.prob_thresh_plot_checks_n.setRange(1, 100)
        self.prob_thresh_plot_checks_n.setValue(5)

        form2.addRow("Iterations", self.prob_thresh_rep_num)
        form2.addRow("Tail percentile", self.prob_thresh_tail)
        form2.addRow("Plot random checks", self.prob_thresh_plot_checks)
        form2.addRow("Number of checks to plot", self.prob_thresh_plot_checks_n)

        layout.addWidget(sttc_box)
        layout.addWidget(adj_box)
        layout.addWidget(thr_box)
        layout.addStretch()

    def load(self, params: Params) -> None:
        self.lag_vals.setText(", ".join(str(v) for v in params.func_con_lag_val))
        self.trunc_rec.setChecked(params.trunc_rec)
        self.trunc_length.setValue(params.trunc_length)
        if params.adj_m_type == "binary":
            self.binary_btn.setChecked(True)
        else:
            self.weighted_btn.setChecked(True)
        self.prob_thresh_rep_num.setValue(params.prob_thresh_rep_num)
        self.prob_thresh_tail.setValue(params.prob_thresh_tail)
        self.prob_thresh_plot_checks.setChecked(params.prob_thresh_plot_checks)
        self.prob_thresh_plot_checks_n.setValue(params.prob_thresh_plot_checks_n)

    def save(self, params: Params) -> None:
        raw = self.lag_vals.text().strip()
        params.func_con_lag_val = [int(x) for x in raw.split(",") if x.strip()]
        params.trunc_rec = self.trunc_rec.isChecked()
        params.trunc_length = self.trunc_length.value()
        params.adj_m_type = "binary" if self.binary_btn.isChecked() else "weighted"
        params.prob_thresh_rep_num = self.prob_thresh_rep_num.value()
        params.prob_thresh_tail = self.prob_thresh_tail.value()
        params.prob_thresh_plot_checks = self.prob_thresh_plot_checks.isChecked()
        params.prob_thresh_plot_checks_n = self.prob_thresh_plot_checks_n.value()
