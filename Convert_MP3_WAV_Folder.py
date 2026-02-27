import os
import sys
from pathlib import Path
import subprocess

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QFileDialog,
                             QProgressBar, QTextEdit, QComboBox, QSpinBox,
                             QGroupBox, QGridLayout, QMessageBox)
from PyQt5.QtGui import QFont, QTextCursor

# Для работы с аудио
from pydub import AudioSegment
from pydub.utils import which


# Указываем путь к FFmpeg
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\ffmpeg\bin\ffprobe.exe"

# Проверяем и устанавливаем пути
if os.path.exists(FFMPEG_PATH):
    AudioSegment.converter = FFMPEG_PATH
    print(f"✅ FFmpeg найден: {FFMPEG_PATH}")
else:
    print(f"❌ FFmpeg не найден по пути: {FFMPEG_PATH}")
    AudioSegment.converter = which("ffmpeg")
    if AudioSegment.converter:
        print(f"✅ FFmpeg найден в системе: {AudioSegment.converter}")

if os.path.exists(FFPROBE_PATH):
    AudioSegment.ffprobe = FFPROBE_PATH
    print(f"✅ FFprobe найден: {FFPROBE_PATH}")
else:
    AudioSegment.ffprobe = which("ffprobe")
    if AudioSegment.ffprobe:
        print(f"✅ FFprobe найден в системе: {AudioSegment.ffprobe}")


class ConverterWorker(QThread):
    """
    Поток для конвертации, чтобы не блокировать интерфейс.
    """
    progress_updated = pyqtSignal(int, int)  # текущий файл, всего файлов
    log_message = pyqtSignal(str)
    conversion_finished = pyqtSignal(bool, str)  # успех, сообщение

    def __init__(self, input_dir, output_dir, sample_rate, sample_width):
        """
        sample_width: 2 для 16-bit, 3 для 24-bit, 4 для 32-bit
        """
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.sample_rate = sample_rate
        self.sample_width = sample_width

    def run(self):
        try:
            # Поиск всех mp3 файлов в папке (рекурсивно)
            mp3_files = []
            for root, dirs, files in os.walk(self.input_dir):
                for file in files:
                    if file.lower().endswith('.mp3'):
                        full_path = os.path.join(root, file)
                        mp3_files.append(full_path)

            if not mp3_files:
                self.log_message.emit("❌ MP3 файлы не найдены в указанной папке.")
                self.conversion_finished.emit(False, "Нет файлов для конвертации.")
                return

            # Создаем выходную папку, если её нет
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

            total_files = len(mp3_files)
            # Определяем название разрядности для лога
            bit_depth = {2: "16-bit", 3: "24-bit", 4: "32-bit"}.get(self.sample_width, f"{self.sample_width*8}-bit")
            self.log_message.emit(f"🎵 Найдено файлов: {total_files}")
            self.log_message.emit(f"⚙️ Параметры: {self.sample_rate} Гц, {bit_depth}")

            # Определяем кодек в зависимости от разрядности
            if self.sample_width == 2:
                codec = "pcm_s16le"  # 16-bit little-endian
            elif self.sample_width == 3:
                codec = "pcm_s24le"  # 24-bit little-endian
            elif self.sample_width == 4:
                codec = "pcm_s32le"  # 32-bit little-endian
            else:
                codec = "pcm_s16le"  # по умолчанию

            for idx, mp3_path in enumerate(mp3_files):
                try:
                    # Формируем относительный путь для сохранения структуры
                    relative_path = os.path.relpath(mp3_path, self.input_dir)
                    # Меняем расширение на .wav
                    wav_relative = Path(relative_path).with_suffix('.wav')
                    wav_output = os.path.join(self.output_dir, wav_relative)

                    # Создаем подпапки в выходной директории при необходимости
                    Path(os.path.dirname(wav_output)).mkdir(parents=True, exist_ok=True)

                    self.log_message.emit(f"[{idx+1}/{total_files}] Конвертация: {relative_path}")

                    # Используем прямой вызов ffmpeg для большей надежности
                    cmd = [
                        AudioSegment.converter,
                        "-i", f'"{mp3_path}"',  # Кавычки для путей с пробелами
                        "-ar", str(self.sample_rate),
                        "-acodec", codec,
                        "-y",  # Перезаписывать выходной файл
                        f'"{wav_output}"'
                    ]
                    
                    # Объединяем команду в строку
                    cmd_str = " ".join(cmd)
                    
                    # Выполняем команду
                    result = subprocess.run(
                        cmd_str,
                        shell=True,
                        capture_output=True,
                        text=True,
                        encoding='utf-8'
                    )
                    
                    if result.returncode == 0:
                        self.log_message.emit(f"✅ Готово: {wav_relative}")
                    else:
                        error_msg = result.stderr.strip() if result.stderr else "Неизвестная ошибка"
                        self.log_message.emit(f"❌ Ошибка с файлом {relative_path}: {error_msg}")

                except Exception as e:
                    self.log_message.emit(f"❌ Ошибка с файлом {relative_path}: {str(e)}")

                # Обновляем прогресс
                self.progress_updated.emit(idx + 1, total_files)

            self.log_message.emit("🎉 Конвертация завершена!")
            self.conversion_finished.emit(True, "Все файлы обработаны.")

        except Exception as e:
            self.log_message.emit(f"🔥 Критическая ошибка: {str(e)}")
            self.conversion_finished.emit(False, str(e))


class ConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("MP3 to WAV Конвертер")
        self.setGeometry(200, 200, 900, 700)

        # Увеличиваем шрифт по умолчанию на 2pt
        default_font = QApplication.font()
        default_font.setPointSize(default_font.pointSize() + 2)
        QApplication.setFont(default_font)

        # Основной layout
        main_layout = QVBoxLayout()

        # === Информация о FFmpeg ===
        ffmpeg_info = QLabel()
        ffprobe_info = QLabel()
        
        if AudioSegment.converter and os.path.exists(AudioSegment.converter):
            ffmpeg_info.setText(f"✅ FFmpeg: {AudioSegment.converter}")
            ffmpeg_info.setStyleSheet("color: green;")
        else:
            ffmpeg_info.setText("❌ FFmpeg не найден! Конвертация невозможна.")
            ffmpeg_info.setStyleSheet("color: red;")
        
        if AudioSegment.ffprobe and os.path.exists(AudioSegment.ffprobe):
            ffprobe_info.setText(f"✅ FFprobe: {AudioSegment.ffprobe}")
            ffprobe_info.setStyleSheet("color: green;")
        else:
            ffprobe_info.setText("⚠️ FFprobe не найден (не критично для конвертации)")
            ffprobe_info.setStyleSheet("color: orange;")
        
        main_layout.addWidget(ffmpeg_info)
        main_layout.addWidget(ffprobe_info)

        # === Группа выбора папок ===
        folder_group = QGroupBox("Выбор папок")
        folder_layout = QGridLayout()

        # Исходная папка
        folder_layout.addWidget(QLabel("Исходная папка (MP3):"), 0, 0)
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("Выберите папку с MP3 файлами...")
        folder_layout.addWidget(self.input_path_edit, 0, 1)
        self.input_browse_btn = QPushButton("Обзор...")
        self.input_browse_btn.clicked.connect(self.browse_input_folder)
        folder_layout.addWidget(self.input_browse_btn, 0, 2)

        # Выходная папка
        folder_layout.addWidget(QLabel("Папка для WAV:"), 1, 0)
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Выберите папку для сохранения...")
        folder_layout.addWidget(self.output_path_edit, 1, 1)
        self.output_browse_btn = QPushButton("Обзор...")
        self.output_browse_btn.clicked.connect(self.browse_output_folder)
        folder_layout.addWidget(self.output_browse_btn, 1, 2)

        folder_group.setLayout(folder_layout)
        main_layout.addWidget(folder_group)

        # === Группа настроек конвертации ===
        settings_group = QGroupBox("Настройки WAV")
        settings_layout = QGridLayout()

        # Частота дискретизации
        settings_layout.addWidget(QLabel("Частота дискретизации (Гц):"), 0, 0)
        self.sample_rate_combo = QComboBox()
        sample_rates = ["8000", "11025", "16000", "22050", "32000", "44100", "48000", "88200", "96000", "192000"]
        self.sample_rate_combo.addItems(sample_rates)
        self.sample_rate_combo.setCurrentText("48000")  # По умолчанию 48kHz
        settings_layout.addWidget(self.sample_rate_combo, 0, 1)

        # Разрядность (sample width)
        settings_layout.addWidget(QLabel("Разрядность:"), 1, 0)
        self.bit_depth_combo = QComboBox()
        bit_depths = [
            "16-bit (стандарт)",
            "24-bit (профессиональный)",
            "32-bit (максимальный)"
        ]
        self.bit_depth_combo.addItems(bit_depths)
        self.bit_depth_combo.setCurrentIndex(2)  # 32-bit по умолчанию
        settings_layout.addWidget(self.bit_depth_combo, 1, 1)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # === Кнопка запуска ===
        self.convert_btn = QPushButton("🚀 Начать конвертацию")
        self.convert_btn.setMinimumHeight(40)
        self.convert_btn.clicked.connect(self.start_conversion)
        main_layout.addWidget(self.convert_btn)

        # === Прогресс бар ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # === Лог выполнения ===
        log_label = QLabel("Лог выполнения:")
        main_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFontFamily("Courier")  # Моноширинный шрифт для лога
        main_layout.addWidget(self.log_text)

        self.setLayout(main_layout)

    def browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с MP3")
        if folder:
            self.input_path_edit.setText(folder)
            # Если выходная папка не указана, предлагаем ту же
            if not self.output_path_edit.text():
                self.output_path_edit.setText(folder)

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения WAV")
        if folder:
            self.output_path_edit.setText(folder)

    def log(self, message):
        """Добавляет сообщение в лог и прокручивает вниз."""
        self.log_text.append(message)
        # Прокрутка вниз
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def get_sample_width(self):
        """Преобразует выбор разрядности в sample_width."""
        index = self.bit_depth_combo.currentIndex()
        # 2 для 16-bit, 3 для 24-bit, 4 для 32-bit
        return {0: 2, 1: 3, 2: 4}.get(index, 2)

    def start_conversion(self):
        """Запускает процесс конвертации в отдельном потоке."""
        # Проверка наличия ffmpeg
        if not AudioSegment.converter or not os.path.exists(AudioSegment.converter):
            QMessageBox.critical(self, "Ошибка",
                                 "FFmpeg не найден. Убедитесь, что путь C:\\ffmpeg\\bin\\ffmpeg.exe существует\n"
                                 "или установите FFmpeg и добавьте его в PATH.")
            return

        input_dir = self.input_path_edit.text().strip()
        output_dir = self.output_path_edit.text().strip()

        if not input_dir or not output_dir:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите исходную и выходную папки.")
            return

        if not os.path.isdir(input_dir):
            QMessageBox.warning(self, "Ошибка", "Исходная папка не существует.")
            return

        # Создаем выходную папку, если её нет
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать выходную папку:\n{str(e)}")
            return

        # Получаем настройки
        sample_rate = int(self.sample_rate_combo.currentText())
        sample_width = self.get_sample_width()
        bit_depth_name = {2: "16-bit", 3: "24-bit", 4: "32-bit"}[sample_width]

        # Блокируем кнопку на время конвертации
        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("⏳ Конвертация...")
        self.progress_bar.setValue(0)
        self.log_text.clear()

        self.log(f"📁 Вход: {input_dir}")
        self.log(f"📁 Выход: {output_dir}")
        self.log(f"⚙️ Частота: {sample_rate} Гц, Разрядность: {bit_depth_name}")
        self.log(f"🔧 FFmpeg: {AudioSegment.converter}")
        if AudioSegment.ffprobe:
            self.log(f"🔧 FFprobe: {AudioSegment.ffprobe}")

        # Создаем и запускаем рабочий поток
        self.worker = ConverterWorker(input_dir, output_dir, sample_rate, sample_width)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.log_message.connect(self.log)
        self.worker.conversion_finished.connect(self.on_finished)
        self.worker.start()

    def update_progress(self, current, total):
        """Обновление прогресс-бара."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_finished(self, success, message):
        """Обработка завершения конвертации."""
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("🚀 Начать конвертацию")

        if success:
            self.log("✅✅✅ Конвертация успешно завершена!")
        else:
            self.log(f"❌❌❌ Ошибка: {message}")
            QMessageBox.critical(self, "Ошибка", f"Конвертация прервана:\n{message}")

        self.worker = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConverterApp()
    window.show()
    sys.exit(app.exec_())