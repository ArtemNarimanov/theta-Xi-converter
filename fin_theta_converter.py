#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Конвертер данных теплового расчёта плоского ребра в безразмерные координаты.

Вычисляется:
    ξ = x / L
    θ = (T - T1) / (T0 - T1)

по данным .dat-файлов с координатой x (м) и температурой T (K).
Результат — два файла (по умолчанию xi.dat и theta.dat), готовые
для построения графика θ(ξ).

Портативное приложение: только стандартная библиотека Python 3.9+,
GUI на tkinter, установка не требуется. Файл можно переименовать
в fin_theta_converter.pyw и запускать двойным кликом без консоли.
"""

import math
import os
import re
import subprocess
import sys
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

# Регулярное выражение для чисел в обычном и научном форматах:
# 0.01, 1e-3, -2.5, +3.14. Lookbehind исключает цифры из идентификаторов
# (например, "9" внутри заголовка "LAB9"), чтобы их не принимать за числа.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)


# ---------------------------------------------------------------------------
# Разбор входных файлов
# ---------------------------------------------------------------------------

def _extract_numbers(line):
    """Извлечь все числовые значения из строки (нечисловые токены игнорируются)."""
    result = []
    for token in _NUMBER_RE.findall(line):
        try:
            result.append(float(token))
        except ValueError:
            continue
    return result


def _read_lines(path, log=None):
    """Прочитать текст файла; при ошибке бросить ValueError с понятным сообщением."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {path}")
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise ValueError(f"Не удалось прочитать файл {path}: {exc}") from exc


def _parse_values(path, start_line=1, log=None):
    """Прочитать список числовых значений из файла (числа из всех строк).

    Пустые строки и комментарии (#, %, //) игнорируются. Строка без чисел
    считается заголовком/комментарием — пропускается с предупреждением.
    """
    log = log or (lambda msg: None)
    lines = _read_lines(path, log)
    values = []
    for line_no, raw in enumerate(lines, start=1):
        if line_no < start_line:
            continue  # строки до стартовой — пропускаются без предупреждения
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", "%", "//")):
            continue
        nums = _extract_numbers(line)
        if not nums:
            log(f"Предупреждение: строка {line_no} файла {Path(path).name} "
                f"не содержит чисел — пропущена")
            continue
        values.extend(nums)
    return values


def parse_separate_files(x_path, t_path, start_line_x=1, start_line_t=1, log=None):
    """Прочитать x и T из двух отдельных файлов.

    В каждом файле ожидается одно число на строку (допустимо и больше).
    Если количество значений не совпадает — используется минимальное
    количество с предупреждением в логе. Возвращает список пар (x, T).
    """
    log = log or (lambda msg: None)
    x_values = _parse_values(x_path, start_line_x, log)
    t_values = _parse_values(t_path, start_line_t, log)
    n = min(len(x_values), len(t_values))
    if len(x_values) != len(t_values):
        log(f"Предупреждение: количество значений не совпадает "
            f"(x: {len(x_values)}, T: {len(t_values)}); "
            f"используются первые {n} значений")
    return list(zip(x_values[:n], t_values[:n]))


# ---------------------------------------------------------------------------
# Расчёты и запись результатов
# ---------------------------------------------------------------------------

def convert_data(data, L, T0, T1, log=None):
    """Вычислить ξ = x/L и θ = (T - T1)/(T0 - T1).

    Возвращает кортеж (xi, theta) — списки безразмерных значений.
    Пары сортируются по возрастанию x, чтобы ξ был монотонным.
    """
    log = log or (lambda msg: None)
    if not math.isfinite(L) or L <= 0:
        raise ValueError("L должно быть конечным числом, строго больше 0")
    if not math.isfinite(T0) or not math.isfinite(T1):
        raise ValueError("T0 и T1 должны быть конечными числами")

    # Сортировка по возрастанию x — ξ будет монотонным в выходных файлах
    data = sorted(data, key=lambda pair: pair[0])

    # Отбрасываем неконечные значения (NaN, inf) с предупреждением
    clean = []
    for x, t in data:
        if math.isfinite(x) and math.isfinite(t):
            clean.append((x, t))
        else:
            log(f"Предупреждение: пропущено неконечное значение (x={x}, T={t})")
    if not clean:
        raise ValueError("После отбора в входных данных не осталось ни одной пары")

    # Проверка физического диапазона x ∈ [0, L]; значения не удаляем, только предупреждаем
    tol = 1e-9 * L
    out_of_range = [x for x, _ in clean if x < -tol or x > L + tol]
    if out_of_range:
        example = ", ".join(f"x={x:g}" for x in out_of_range[:5])
        log(f"Предупреждение: {len(out_of_range)} значений x вне диапазона [0, L] "
            f"(например: {example}); значения сохраняются")

    denom = T0 - T1
    xi = []
    theta = []
    if abs(denom) < 1e-12:
        # Особый случай: деление на ноль не выполняем, θ ≡ 0
        log("Предупреждение: T0 и T1 практически равны, θ принят равным нулю")
        for x, _ in clean:
            xi.append(x / L)
            theta.append(0.0)
    else:
        for x, t in clean:
            xi.append(x / L)
            theta.append((t - T1) / denom)
    return xi, theta


def write_output(xi_values, theta_values, xi_path, theta_path, log=None):
    """Записать ξ и θ в файлы.

    Числовой формат повторяет входные файлы:
    - ξ — одна строка, значения через «;» с завершающим «;», формат %.4f (как x.dat);
    - θ — по 16 значений в строке, формат %.4E (как result_tav.dat).
    Без заголовков и служебных рядов.

    Если папка вывода не существует — создаётся (вместе с родителями).
    Возвращает список записанных полных путей.
    """
    log = log or (lambda msg: None)
    xi_path = Path(xi_path)
    theta_path = Path(theta_path)

    for target in (xi_path, theta_path):
        parent = target.parent
        if not parent.exists():
            log(f"Предупреждение: папка {parent} не существует — создаю")
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ValueError(f"Не удалось создать папку {parent}: {exc}") from exc

    # ξ: одна строка через «;» с завершающим «;», формат как в x.dat
    xi_line = ";".join(f"{v:.4f}" for v in xi_values) + ";"
    try:
        with open(xi_path, "w", encoding="utf-8") as fh:
            fh.write(xi_line + "\n")
    except OSError as exc:
        raise ValueError(f"Не удалось записать файл {xi_path}: {exc}") from exc
    log(f"Создан файл: {xi_path} ({len(xi_values)} значений)")

    # θ: по 16 значений в строке, формат как в result_tav.dat
    lines = []
    for i in range(0, len(theta_values), 16):
        chunk = theta_values[i:i + 16]
        lines.append("  ".join(f"{v:.4E}" for v in chunk))
    try:
        with open(theta_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        raise ValueError(f"Не удалось записать файл {theta_path}: {exc}") from exc
    log(f"Создан файл: {theta_path} ({len(theta_values)} значений)")

    return [xi_path, theta_path]


# ---------------------------------------------------------------------------
# Графический интерфейс
# ---------------------------------------------------------------------------

class FinConverterApp:
    """Главное окно приложения (tkinter)."""

    def __init__(self, root):
        self.root = root
        root.title("Конвертер данных ребра: θ(ξ)")
        root.geometry("700x760")
        root.minsize(620, 560)

        self._build_ui()

    # ---------------- построение интерфейса ----------------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Параметры расчёта ---
        params = ttk.LabelFrame(main, text="Параметры расчёта")
        params.pack(fill=tk.X, **pad)
        self.entry_L = self._add_param_row(params, 0, "L — высота охлаждаемой части, м", "0.060")
        # T0/T1 вводятся в °C; справа отображается значение в К (T = t + 273.15)
        self.label_T0_K = ttk.Label(params, text="")
        self.entry_T0 = self._add_param_row(params, 1, "T0 — температура основания, °C", "120.0",
                                            right_label=self.label_T0_K)
        self.label_T1_K = ttk.Label(params, text="")
        self.entry_T1 = self._add_param_row(params, 2, "T1 — температура воздуха, °C", "20.0",
                                            right_label=self.label_T1_K)
        for entry in (self.entry_T0, self.entry_T1):
            entry.bind("<KeyRelease>", self._update_k_labels)
            entry.bind("<FocusOut>", self._update_k_labels)
        self._update_k_labels()

        # --- Входные данные ---
        inputs = ttk.LabelFrame(main, text="Входные данные (.dat)")
        inputs.pack(fill=tk.X, **pad)

        # Файл с x: своя стартовая строка данных
        ttk.Label(inputs, text="Файл с x:").grid(row=0, column=0, sticky=tk.W, padx=8)
        self.btn_file_x = ttk.Button(inputs, text="Файл с x…",
                                     command=lambda: self._pick_file(self.entry_file_x))
        self.btn_file_x.grid(row=0, column=1, padx=4)
        self.entry_file_x = ttk.Entry(inputs, width=38)
        self.entry_file_x.grid(row=0, column=2, columnspan=2, sticky=tk.EW, padx=4)
        ttk.Label(inputs, text="строка начала:").grid(row=0, column=4, padx=4)
        self.entry_start_x = ttk.Entry(inputs, width=5)
        self.entry_start_x.insert(0, "1")
        self.entry_start_x.grid(row=0, column=5, padx=8)

        # Файл с T: своя стартовая строка данных
        ttk.Label(inputs, text="Файл с T:").grid(row=1, column=0, sticky=tk.W, padx=8)
        self.btn_file_t = ttk.Button(inputs, text="Файл с T…", command=self._pick_file_t)
        self.btn_file_t.grid(row=1, column=1, padx=4)
        self.entry_file_t = ttk.Entry(inputs, width=38)
        self.entry_file_t.grid(row=1, column=2, columnspan=2, sticky=tk.EW, padx=4)
        ttk.Label(inputs, text="строка начала:").grid(row=1, column=4, padx=4)
        self.entry_start_t = ttk.Entry(inputs, width=5)
        self.entry_start_t.insert(0, "4")  # для GraphLab T данные обычно со строки 4
        self.entry_start_t.grid(row=1, column=5, padx=8)

        inputs.columnconfigure(2, weight=1)

        # --- Выходные данные ---
        outputs = ttk.LabelFrame(main, text="Выходные данные")
        outputs.pack(fill=tk.X, **pad)

        ttk.Label(outputs, text="Папка вывода:").grid(row=0, column=0, sticky=tk.W, padx=8)
        self.btn_out_dir = ttk.Button(outputs, text="Выбрать папку…",
                                      command=self._pick_out_dir)
        self.btn_out_dir.grid(row=0, column=1, padx=4)
        self.entry_out_dir = ttk.Entry(outputs, width=52)
        self.entry_out_dir.grid(row=0, column=2, columnspan=3, sticky=tk.EW, padx=8)

        ttk.Label(outputs, text="Имя файла ξ:").grid(row=1, column=0, sticky=tk.W, padx=8)
        self.entry_xi_name = ttk.Entry(outputs, width=24)
        self.entry_xi_name.insert(0, "xi.dat")
        self.entry_xi_name.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=4)
        ttk.Label(outputs, text="Имя файла θ:").grid(row=1, column=3, sticky=tk.W, padx=4)
        self.entry_theta_name = ttk.Entry(outputs, width=24)
        self.entry_theta_name.insert(0, "theta.dat")
        self.entry_theta_name.grid(row=1, column=4, columnspan=2, sticky=tk.EW, padx=8)

        outputs.columnconfigure(2, weight=1)

        # --- Кнопки и лог ---
        buttons = ttk.Frame(main)
        buttons.pack(fill=tk.X, **pad)
        self.btn_convert = ttk.Button(buttons, text="Преобразовать", command=self.on_convert)
        self.btn_convert.pack(side=tk.LEFT, padx=4)
        self.btn_open_dir = ttk.Button(buttons, text="Открыть папку вывода",
                                       command=self._open_out_dir)
        self.btn_open_dir.pack(side=tk.LEFT, padx=4)

        self.log_text = ScrolledText(main, height=16, state=tk.DISABLED,
                                     font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, **pad)

    def _add_param_row(self, parent, row, label, default, right_label=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, padx=8, pady=2)
        entry = ttk.Entry(parent, width=16)
        entry.insert(0, default)
        entry.grid(row=row, column=1, sticky=tk.W, padx=8, pady=2)
        if right_label is not None:
            right_label.grid(row=row, column=2, sticky=tk.W, padx=(16, 8), pady=2)
        return entry

    def _update_k_labels(self, _event=None):
        """Справа от полей °C показать значение в К: T = t + 273.15."""
        for entry, label in ((self.entry_T0, self.label_T0_K),
                             (self.entry_T1, self.label_T1_K)):
            text = entry.get().strip().replace(",", ".")
            try:
                t_c = float(text)
                label.config(text=f"{t_c + 273.15:.2f} К")
            except ValueError:
                label.config(text="—")

    # ---------------- вспомогательные методы ----------------

    def log(self, message):
        """Добавить строку в блок лога."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _pick_file(self, entry):
        """Диалог выбора входного .dat-файла."""
        path = filedialog.askopenfilename(
            title="Выберите .dat-файл",
            filetypes=[("Файлы данных", "*.dat"), ("Все файлы", "*.*")],
        )
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _pick_file_t(self):
        """Диалог выбора файла с T; при выборе предлагается имя для θ."""
        path = filedialog.askopenfilename(
            title="Выберите файл с T (.dat)",
            filetypes=[("Файлы данных", "*.dat"), ("Все файлы", "*.*")],
        )
        if path:
            self._on_t_file_chosen(path)

    def _on_t_file_chosen(self, path):
        """Записать выбранный файл T и при необходимости предложить имя для θ.

        Если имя θ не менялось вручную (дефолт «theta.dat»), предлагается
        вариант по имени файла T: result_tav.dat -> result_theta_tav.dat
        """
        self.entry_file_t.delete(0, tk.END)
        self.entry_file_t.insert(0, path)
        if self.entry_theta_name.get().strip() == "theta.dat":
            name = self._derive_theta_name(path)
            self.entry_theta_name.delete(0, tk.END)
            self.entry_theta_name.insert(0, name)

    @staticmethod
    def _derive_theta_name(t_path):
        """Предложить имя файла θ по имени файла с T.

        result_tav.dat -> result_theta_tav.dat (вставка «theta» перед последним
        сегментом); без подчёркивания: TAV.dat -> theta_TAV.dat
        """
        stem = Path(t_path).stem
        if "_" in stem:
            head, _, tail = stem.rpartition("_")
            return f"{head}_theta_{tail}.dat"
        return f"theta_{stem}.dat"

    def _pick_out_dir(self):
        """Диалог выбора папки вывода."""
        path = filedialog.askdirectory(title="Выберите папку для записи")
        if path:
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, path)

    def _open_out_dir(self):
        """Открыть папку вывода в проводнике (переносимо, без внешних зависимостей)."""
        path = Path(self.entry_out_dir.get().strip())
        if not path.is_dir():
            messagebox.showinfo("Папка вывода", "Папка вывода ещё не существует.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # только Windows, стандартная библиотека
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except (OSError, AttributeError) as exc:
            messagebox.showerror("Не удалось открыть папку", str(exc))

    @staticmethod
    def _parse_float(text, name):
        value = text.strip().replace(",", ".")
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Значение {name} не является числом: «{text.strip()}»")

    @staticmethod
    def _parse_start_line(text, name):
        value = text.strip().replace(",", ".")
        try:
            n = int(float(value))
        except ValueError:
            raise ValueError(f"Строка начала данных {name} не является целым числом: «{text.strip()}»")
        if n < 1:
            raise ValueError(f"Строка начала данных {name} должна быть больше или равна 1")
        return n

    # ---------------- основная операция ----------------

    def on_convert(self):
        """Кнопка «Преобразовать»: полный цикл разбора, расчёта и записи."""
        self.log_text.delete("1.0", tk.END)
        try:
            L = self._parse_float(self.entry_L.get(), "L")
            t0_c = self._parse_float(self.entry_T0.get(), "T0")
            t1_c = self._parse_float(self.entry_T1.get(), "T1")
            # Ввод в °C; пересчёт в К: T = t + 273.15
            T0, T1 = t0_c + 273.15, t1_c + 273.15
            self.log(f"T0 = {t0_c:g} °C = {T0:.2f} К; T1 = {t1_c:g} °C = {T1:.2f} К")

            start_x = self._parse_start_line(self.entry_start_x.get(), "x")
            start_t = self._parse_start_line(self.entry_start_t.get(), "T")
            x_path = self.entry_file_x.get().strip()
            t_path = self.entry_file_t.get().strip()
            if not x_path or not t_path:
                raise ValueError("Выберите файлы с x и с T")
            data = parse_separate_files(x_path, t_path,
                                        start_line_x=start_x, start_line_t=start_t,
                                        log=self.log)

            if not data:
                raise ValueError("Входные данные пусты: не удалось прочитать ни одной пары (x, T)")
            self.log(f"Прочитано пар (x, T): {len(data)}")

            xi, theta = convert_data(data, L, T0, T1, log=self.log)

            out_dir = self.entry_out_dir.get().strip()
            if not out_dir:
                raise ValueError("Выберите папку вывода")
            out_dir_path = Path(out_dir)
            xi_name = self.entry_xi_name.get().strip() or "xi.dat"
            theta_name = self.entry_theta_name.get().strip() or "theta.dat"
            # Если в поле имени указан абсолютный путь — используем его как есть
            xi_path = Path(xi_name) if Path(xi_name).is_absolute() else out_dir_path / xi_name
            theta_path = Path(theta_name) if Path(theta_name).is_absolute() else out_dir_path / theta_name

            write_output(xi, theta, xi_path, theta_path, log=self.log)
            self.log(f"Готово: записано {len(xi)} значений — ξ в «{xi_path.name}», "
                     f"θ в «{theta_path.name}»")
        except Exception as exc:  # noqa: BLE001 — любые ошибки показываем в UI
            self.log(f"Ошибка: {exc}")
            messagebox.showerror("Ошибка преобразования", str(exc))


def main():
    """Точка входа приложения."""
    root = tk.Tk()
    FinConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
