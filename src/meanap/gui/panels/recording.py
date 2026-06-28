"""Recording settings panel."""

from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLineEdit, QVBoxLayout, QWidget,
)

from meanap.params import Params

CHANNEL_LAYOUTS = ["MCS60", "Axion64", "Mea256", "Custom"]
POTENTIAL_UNITS = ["uV", "mV", "V"]


class RecordingPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Sampling ─────────────────────────────────────────────────────────
        sampling_box = QGroupBox("Sampling")
        form = QFormLayout(sampling_box)

        self.fs = QDoubleSpinBox()
        self.fs.setRange(1, 1_000_000)
        self.fs.setDecimals(0)
        self.fs.setSuffix(" Hz")
        self.fs.setValue(25000)

        self.d_samp_f = QDoubleSpinBox()
        self.d_samp_f.setRange(1, 100_000)
        self.d_samp_f.setDecimals(0)
        self.d_samp_f.setSuffix(" Hz")
        self.d_samp_f.setValue(1000)

        form.addRow("Sampling frequency", self.fs)
        form.addRow("Downsample frequency", self.d_samp_f)

        # ── Hardware ─────────────────────────────────────────────────────────
        hw_box = QGroupBox("Hardware")
        form2 = QFormLayout(hw_box)

        self.potential_difference_unit = QComboBox()
        self.potential_difference_unit.addItems(POTENTIAL_UNITS)

        self.channel_layout = QComboBox()
        self.channel_layout.addItems(CHANNEL_LAYOUTS)
        self.channel_layout.setEditable(True)

        form2.addRow("Potential difference unit", self.potential_difference_unit)
        form2.addRow("Channel layout", self.channel_layout)

        layout.addWidget(sampling_box)
        layout.addWidget(hw_box)
        layout.addStretch()

    def load(self, params: Params) -> None:
        self.fs.setValue(params.fs)
        self.d_samp_f.setValue(params.d_samp_f)
        idx = self.potential_difference_unit.findText(params.potential_difference_unit)
        if idx >= 0:
            self.potential_difference_unit.setCurrentIndex(idx)
        idx = self.channel_layout.findText(params.channel_layout)
        if idx >= 0:
            self.channel_layout.setCurrentIndex(idx)
        else:
            self.channel_layout.setCurrentText(params.channel_layout)

    def save(self, params: Params) -> None:
        params.fs = self.fs.value()
        params.d_samp_f = self.d_samp_f.value()
        params.potential_difference_unit = self.potential_difference_unit.currentText()
        params.channel_layout = self.channel_layout.currentText()
