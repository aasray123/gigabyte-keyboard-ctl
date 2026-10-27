"""PyQt6 control panel for the GIGABYTE GAMING A16 keyboard backlight."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import config
from .config import Settings, parse_color, to_hex
from .device import DeviceError, LampArray
from .effects import EffectRunner


def _icon(rgb: tuple[int, int, int]) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(80, 80, 80))
    painter.setBrush(QColor(*rgb))
    painter.drawRoundedRect(3, 3, 58, 58, 14, 14)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self, lamp: LampArray, settings: Settings) -> None:
        super().__init__()
        self.lamp = lamp
        self.settings = settings
        self.runner: EffectRunner | None = None
        self._updating = False

        self.setWindowTitle("GIGABYTE A16 keyboard backlight")
        self.setMinimumWidth(430)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = lamp.info()
        title = QLabel("<b>Keyboard backlight</b>")
        subtitle = QLabel(
            f"GIGABYTE GAMING A16 · {info.lamp_count} RGB zone · "
            f"{info.vendor_id}:{info.product_id}"
        )
        subtitle.setStyleSheet("color: #888;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # -- colour ---------------------------------------------------------
        colour_box = QGroupBox("Colour")
        colour_layout = QVBoxLayout(colour_box)
        self.swatch = QPushButton()
        self.swatch.setMinimumHeight(58)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.clicked.connect(self.choose_colour)
        colour_layout.addWidget(self.swatch)

        hex_row = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setPlaceholderText("RRGGBB")
        self.hex_edit.returnPressed.connect(self.apply_hex)
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply_hex)
        hex_row.addWidget(QLabel("#"))
        hex_row.addWidget(self.hex_edit, 1)
        hex_row.addWidget(apply_button)
        colour_layout.addLayout(hex_row)

        presets = QGridLayout()
        presets.setSpacing(6)
        for index, (hex_value, name) in enumerate(config.PRESETS):
            button = QPushButton()
            button.setFixedSize(34, 34)
            button.setToolTip(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: #{hex_value}; border: 1px solid "
                f"#666; border-radius: 7px; }}"
                f"QPushButton:hover {{ border: 2px solid #bbb; }}"
            )
            button.clicked.connect(
                lambda _checked=False, value=hex_value: self.set_colour(value)
            )
            presets.addWidget(button, index // 6, index % 6)
        colour_layout.addLayout(presets)
        layout.addWidget(colour_box)

        # -- brightness -----------------------------------------------------
        brightness_box = QGroupBox("Brightness")
        brightness_layout = QHBoxLayout(brightness_box)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(settings.brightness)
        self.brightness_slider.valueChanged.connect(self.set_brightness)
        self.brightness_value = QLabel(f"{settings.brightness}%")
        self.brightness_value.setFixedWidth(42)
        self.brightness_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        brightness_layout.addWidget(self.brightness_slider, 1)
        brightness_layout.addWidget(self.brightness_value)
        layout.addWidget(brightness_box)

        # -- effect ---------------------------------------------------------
        effect_box = QGroupBox("Effect")
        effect_layout = QGridLayout(effect_box)
        self.effect_combo = QComboBox()
        self.effect_combo.addItems(list(config.EFFECTS))
        self.effect_combo.setCurrentText(settings.effect)
        self.effect_combo.currentTextChanged.connect(self.set_effect)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(settings.speed)
        self.speed_slider.valueChanged.connect(self.set_speed)
        self.speed_value = QLabel(f"{settings.speed}%")
        self.speed_value.setFixedWidth(42)
        self.speed_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        effect_layout.addWidget(QLabel("Mode"), 0, 0)
        effect_layout.addWidget(self.effect_combo, 0, 1)
        effect_layout.addWidget(QLabel("Speed"), 1, 0)
        effect_layout.addWidget(self.speed_slider, 1, 1)
        effect_layout.addWidget(self.speed_value, 1, 2)
        effect_note = QLabel(
            "Single-zone keyboard: 'wave' sweeps the palette in reading order "
            "(top row left to right, then bottom row), one colour at a time."
        )
        effect_note.setWordWrap(True)
        effect_note.setStyleSheet("color: #888;")
        effect_layout.addWidget(effect_note, 2, 0, 1, 3)
        layout.addWidget(effect_box)

        # -- firmware mode --------------------------------------------------
        mode_box = QGroupBox("Keyboard firmware control")
        mode_layout = QVBoxLayout(mode_box)
        self.auto_check = QCheckBox("Let the keyboard handle Fn+Space")
        self.auto_check.setChecked(settings.autonomous)
        self.auto_check.toggled.connect(self.set_autonomous)
        note = QLabel(
            "In firmware mode Fn+Space cycles brightness, but the colour is "
            "the one stored by Gigabyte Control Center (and may be off after "
            "a full power-off)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        mode_layout.addWidget(self.auto_check)
        mode_layout.addWidget(note)
        layout.addWidget(mode_box)

        # -- footer ---------------------------------------------------------
        footer = QHBoxLayout()
        self.power_button = QPushButton()
        self.power_button.setMinimumHeight(38)
        self.power_button.clicked.connect(self.toggle_power)
        self.status = QLabel()
        self.status.setStyleSheet("color: #888;")
        footer.addWidget(self.power_button)
        footer.addWidget(self.status, 1)
        layout.addLayout(footer)

        # -- tray -----------------------------------------------------------
        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setToolTip("GIGABYTE A16 keyboard backlight")
            tray_menu = QMenu()
            show_action = QAction("Show window", self)
            show_action.triggered.connect(self.show_window)
            tray_menu.addAction(show_action)
            power_action = QAction("Toggle backlight", self)
            power_action.triggered.connect(self.toggle_power)
            tray_menu.addAction(power_action)
            tray_menu.addSeparator()
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self.quit_app)
            tray_menu.addAction(quit_action)
            self.tray.setContextMenu(tray_menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()

        self.refresh_ui()
        self.restore_state()

        self.error_timer = QTimer(self)
        self.error_timer.timeout.connect(self.check_effect_error)
        self.error_timer.start(1000)

    # -- UI helpers ---------------------------------------------------------

    def refresh_ui(self) -> None:
        rgb = self.settings.rgb()
        hex_value = to_hex(rgb)
        self._updating = True
        try:
            self.swatch.setText(f"#{hex_value}")
            self.swatch.setStyleSheet(
                f"QPushButton {{ background: #{hex_value}; color: "
                f"{'#000' if sum(rgb) > 380 else '#fff'}; border: 1px solid "
                f"#666; border-radius: 8px; font-weight: bold; font-size: 15px; }}"
            )
            self.hex_edit.setText(hex_value)
            self.brightness_slider.setValue(self.settings.brightness)
            self.brightness_value.setText(f"{self.settings.brightness}%")
            self.speed_slider.setValue(self.settings.speed)
            self.speed_value.setText(f"{self.settings.speed}%")
            if self.effect_combo.currentText() != self.settings.effect:
                self.effect_combo.setCurrentText(self.settings.effect)
            self.auto_check.setChecked(self.settings.autonomous)
            self.power_button.setText(
                "Turn backlight off" if self.settings.on else "Turn backlight on"
            )
            self.status.setText(
                "Firmware mode" if self.settings.autonomous else "Host mode"
            )
            self.setWindowIcon(_icon(rgb))
            if self.tray is not None:
                self.tray.setIcon(_icon(rgb))
        finally:
            self._updating = False

    def restore_state(self) -> None:
        if self.settings.autonomous:
            self.lamp.set_autonomous(True)
        elif not self.settings.on:
            self.lamp.off()
        elif self.settings.effect == "static":
            self.lamp.set_color(self.settings.rgb(), self.settings.brightness)
        else:
            self.start_effect()

    def start_effect(self) -> None:
        if self.runner is None:
            self.runner = EffectRunner(self.lamp, self.settings)
        else:
            self.runner.update(self.settings)
        self.runner.start()

    def stop_effect(self, *, apply_static: bool = True) -> None:
        if self.runner is not None:
            self.runner.stop(apply_static=apply_static)
            self.runner = None

    def apply_now(self) -> None:
        if self.settings.autonomous:
            self.stop_effect(apply_static=False)
            self.lamp.set_autonomous(True)
        elif not self.settings.on:
            self.stop_effect(apply_static=False)
            self.lamp.off()
        elif self.settings.effect == "static":
            self.stop_effect(apply_static=False)
            self.lamp.set_color(self.settings.rgb(), self.settings.brightness)
        else:
            self.start_effect()

    # -- actions ------------------------------------------------------------

    def choose_colour(self) -> None:
        current = QColor(*self.settings.rgb())
        colour = QColorDialog.getColor(current, self, "Keyboard colour")
        if colour.isValid():
            self.set_colour(to_hex((colour.red(), colour.green(), colour.blue())))

    def set_colour(self, value: str) -> None:
        try:
            rgb = parse_color(value)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.settings.color = to_hex(rgb)
        self.settings.on = bool(any(rgb))
        self.settings.autonomous = False
        self.save()
        self.refresh_ui()
        self.apply_now()

    def apply_hex(self) -> None:
        self.set_colour(self.hex_edit.text())

    def set_brightness(self, value: int) -> None:
        if self._updating:
            return
        self.settings.brightness = value
        self.settings.on = value > 0
        self.settings.autonomous = False
        self.brightness_value.setText(f"{value}%")
        self.save()
        self.refresh_ui()
        self.apply_now()

    def set_effect(self, name: str) -> None:
        if self._updating:
            return
        self.settings.effect = name
        self.settings.on = True
        self.settings.autonomous = False
        self.save()
        self.refresh_ui()
        self.apply_now()

    def set_speed(self, value: int) -> None:
        if self._updating:
            return
        self.settings.speed = value
        self.speed_value.setText(f"{value}%")
        self.save()
        if self.runner is not None:
            self.runner.update(self.settings)

    def set_autonomous(self, enabled: bool) -> None:
        if self._updating:
            return
        self.settings.autonomous = enabled
        self.save()
        self.refresh_ui()
        self.apply_now()

    def toggle_power(self) -> None:
        self.settings.on = not self.settings.on
        self.settings.autonomous = False
        if self.settings.on and self.settings.brightness == 0:
            self.settings.brightness = 100
        self.save()
        self.refresh_ui()
        self.apply_now()

    def save(self) -> None:
        try:
            config.save(self.settings)
        except OSError as exc:
            self.status.setText(f"Could not save settings: {exc}")

    def check_effect_error(self) -> None:
        if self.runner is not None and self.runner.error is not None:
            error = self.runner.error
            self.stop_effect(apply_static=False)
            self.status.setText(f"Device error: {error}")
            QMessageBox.warning(self, "Keyboard error", str(error))

    # -- window / tray ------------------------------------------------------

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.tray is not None and self.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self) -> None:
        self.stop_effect(apply_static=True)
        self.lamp.close()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("gigabyte-kbd")
    app.setApplicationDisplayName("GIGABYTE A16 keyboard backlight")
    app.setDesktopFileName("gigabyte-kbd")

    settings = config.load()
    try:
        lamp = LampArray(
            vendor_id=settings.vendor_id,
            product_id=settings.product_id or None,
        ).open()
    except DeviceError as exc:
        QMessageBox.critical(None, "Keyboard not found", str(exc))
        return 1

    window = MainWindow(lamp, settings)
    window.show()
    return app.exec()
