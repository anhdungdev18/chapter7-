from __future__ import annotations

import importlib.util
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Dict, List


def _load_module(filename: str, module_name: str):
    module_path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Không thể nạp module từ {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


module_7A = _load_module("7A.py", "module_7A")
QueryResult = module_7A.QueryResult
VideoSegmentSystem = module_7A.VideoSegmentSystem
build_demo_system = module_7A.build_demo_system


class Chapter7App:
    def __init__(self, root: tk.Tk, system: VideoSegmentSystem):
        self.root = root
        self.system = system
        self.function_names = [
            "FindVideoWithObject",
            "FindVideoWithActivity",
            "FindVideoWithActivityandProp",
            "FindVideoWithObjectandProp",
            "FindObjectsInVideo",
            "FindActivitiesInVideo",
            "FindActivitiesAndPropsinVideo",
            "FindObjectsAndPropsinVideo",
            "DemonstrateAccess",
        ]
        self.combine_function_names = [
            "FindVideoWithObject",
            "FindVideoWithActivity",
            "FindVideoWithActivityandProp",
            "FindVideoWithObjectandProp",
        ]
        self.combine_rows: List[Dict[str, Any]] = []
        self.combine_rows_frame: ttk.Frame | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.root.title("Chapter 7 RS-tree Demo")
        self.root.geometry("1220x820")

        container = ttk.Frame(self.root, padding=8)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        main = ttk.Frame(canvas, padding=16)
        canvas_window = canvas.create_window((0, 0), window=main, anchor="nw")

        def _sync_scrollregion(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        main.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)
        self._bind_mousewheel(canvas)

        ttk.Label(main, text="Hàm truy vấn").grid(row=0, column=0, sticky="w")
        self.function_var = tk.StringVar(value=self.function_names[0])
        function_box = ttk.Combobox(
            main,
            textvariable=self.function_var,
            values=self.function_names,
            state="readonly",
            width=36,
        )
        function_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        function_box.bind("<<ComboboxSelected>>", self._on_function_change)

        self.param_vars: Dict[str, tk.StringVar] = {
            "o": tk.StringVar(),
            "a": tk.StringVar(),
            "p": tk.StringVar(),
            "z": tk.StringVar(),
            "v": tk.StringVar(value="demo_video_01"),
            "s": tk.StringVar(value="1"),
            "e": tk.StringVar(value="100"),
        }
        labels = {
            "o": "Object name",
            "a": "Activity name",
            "p": "Property name",
            "z": "Property value",
            "v": "Video",
            "s": "Start frame",
            "e": "End frame",
        }

        self.entries: Dict[str, ttk.Entry] = {}
        for row_index, key in enumerate(["o", "a", "p", "z", "v", "s", "e"], start=1):
            ttk.Label(main, text=labels[key]).grid(row=row_index, column=0, sticky="w", pady=4)
            entry = ttk.Entry(main, textvariable=self.param_vars[key], width=40)
            entry.grid(row=row_index, column=1, sticky="ew", padx=(8, 0), pady=4)
            self.entries[key] = entry

        button_row = ttk.Frame(main)
        button_row.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Button(button_row, text="Chạy truy vấn", command=self._run_query).pack(side="left")
        ttk.Button(button_row, text="Nạp dữ liệu mẫu", command=self._load_defaults).pack(side="left", padx=8)

        combo_box = ttk.LabelFrame(main, text="Kết hợp truy vấn video", padding=12)
        combo_box.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        toolbar = ttk.Frame(combo_box)
        toolbar.grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="+ Thêm vế", command=self._add_condition_row).pack(side="left")
        ttk.Button(toolbar, text="- Xóa vế", command=self._remove_condition_row).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Chạy truy vấn kết hợp", command=self._run_combined_query).pack(side="left", padx=8)

        self.combine_rows_frame = ttk.Frame(combo_box)
        self.combine_rows_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        combo_box.columnconfigure(0, weight=1)

        self.output = tk.Text(main, wrap="word", font=("Consolas", 10))
        self.output.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

        main.columnconfigure(1, weight=1)
        main.rowconfigure(10, weight=1)

        self._add_condition_row()
        self._add_condition_row()
        self._on_function_change()
        self._load_defaults()

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        def _on_mousewheel(event) -> None:
            delta = -1 if event.delta > 0 else 1
            widget.yview_scroll(delta, "units")

        widget.bind_all("<MouseWheel>", _on_mousewheel)

    def _load_defaults(self) -> None:
        self.param_vars["o"].set("person")
        self.param_vars["a"].set("running")
        self.param_vars["p"].set("location")
        self.param_vars["z"].set("park")
        self.param_vars["v"].set("demo_video_01")
        self.param_vars["s"].set("20")
        self.param_vars["e"].set("80")

        if len(self.combine_rows) >= 1:
            self.combine_rows[0]["query_var"].set("FindVideoWithObject")
            self.combine_rows[0]["param_vars"]["o"].set("person")
        if len(self.combine_rows) >= 2:
            self.combine_rows[1]["operator_var"].set("NOT")
            self.combine_rows[1]["query_var"].set("FindVideoWithObject")
            self.combine_rows[1]["param_vars"]["o"].set("car")

        self._refresh_condition_rows()
        self._run_query()

    def _on_function_change(self, _event=None) -> None:
        required = {
            "FindVideoWithObject": ["o"],
            "FindVideoWithActivity": ["a"],
            "FindVideoWithActivityandProp": ["a", "p", "z"],
            "FindVideoWithObjectandProp": ["o", "p", "z"],
            "FindObjectsInVideo": ["v", "s", "e"],
            "FindActivitiesInVideo": ["v", "s", "e"],
            "FindActivitiesAndPropsinVideo": ["v", "s", "e"],
            "FindObjectsAndPropsinVideo": ["v", "s", "e"],
            "DemonstrateAccess": ["v", "s", "e"],
        }[self.function_var.get()]
        for key, entry in self.entries.items():
            entry.configure(state="normal" if key in required else "disabled")

    def _add_condition_row(self) -> None:
        row = {
            "operator_var": tk.StringVar(value="AND"),
            "query_var": tk.StringVar(value=self.combine_function_names[0]),
            "param_vars": {key: tk.StringVar() for key in ["o", "a", "p", "z"]},
            "operator_widget": None,
            "query_widget": None,
            "param_entries": {},
        }
        self.combine_rows.append(row)
        self._refresh_condition_rows()

    def _remove_condition_row(self) -> None:
        if len(self.combine_rows) <= 2:
            return
        self.combine_rows.pop()
        self._refresh_condition_rows()

    def _refresh_condition_rows(self) -> None:
        if self.combine_rows_frame is None:
            return
        for child in self.combine_rows_frame.winfo_children():
            child.destroy()

        labels = {"o": "Object", "a": "Activity", "p": "Prop", "z": "Value"}
        required_map = {
            "FindVideoWithObject": ["o"],
            "FindVideoWithActivity": ["a"],
            "FindVideoWithActivityandProp": ["a", "p", "z"],
            "FindVideoWithObjectandProp": ["o", "p", "z"],
        }

        for row_index, row in enumerate(self.combine_rows):
            frame = ttk.LabelFrame(self.combine_rows_frame, text=f"Điều kiện {row_index + 1}", padding=8)
            frame.grid(row=row_index, column=0, sticky="ew", pady=6)
            frame.columnconfigure(3, weight=1)

            if row_index == 0:
                ttk.Label(frame, text="Vế đầu tiên").grid(row=0, column=0, sticky="w")
            else:
                ttk.Label(frame, text="Toán tử").grid(row=0, column=0, sticky="w")
                operator_box = ttk.Combobox(
                    frame,
                    textvariable=row["operator_var"],
                    values=["AND", "OR", "NOT"],
                    state="readonly",
                    width=10,
                )
                operator_box.grid(row=0, column=1, sticky="w", padx=(8, 0))
                row["operator_widget"] = operator_box

            ttk.Label(frame, text="Truy vấn").grid(row=0, column=2, sticky="w", padx=(16, 0))
            query_box = ttk.Combobox(
                frame,
                textvariable=row["query_var"],
                values=self.combine_function_names,
                state="readonly",
                width=32,
            )
            query_box.grid(row=0, column=3, sticky="ew", padx=(8, 0))
            query_box.bind("<<ComboboxSelected>>", self._on_dynamic_query_change)
            row["query_widget"] = query_box

            row["param_entries"] = {}
            for offset, key in enumerate(["o", "a", "p", "z"], start=1):
                ttk.Label(frame, text=labels[key]).grid(row=offset, column=2, sticky="w", padx=(16, 0), pady=3)
                entry = ttk.Entry(frame, textvariable=row["param_vars"][key], width=30)
                entry.grid(row=offset, column=3, sticky="ew", padx=(8, 0), pady=3)
                row["param_entries"][key] = entry

            required = required_map[row["query_var"].get()]
            for key, entry in row["param_entries"].items():
                entry.configure(state="normal" if key in required else "disabled")

    def _on_dynamic_query_change(self, _event=None) -> None:
        self._refresh_condition_rows()

    def _run_query(self) -> None:
        try:
            result = self._dispatch()
            self._render_result(result)
        except Exception as error:
            self.output.delete("1.0", tk.END)
            self.output.insert(tk.END, f"Lỗi: {error}")

    def _dispatch(self) -> QueryResult:
        name = self.function_var.get()
        args = {key: value.get().strip() for key, value in self.param_vars.items()}
        methods: Dict[str, Callable[[], QueryResult]] = {
            "FindVideoWithObject": lambda: self.system.FindVideoWithObject(args["o"]),
            "FindVideoWithActivity": lambda: self.system.FindVideoWithActivity(args["a"]),
            "FindVideoWithActivityandProp": lambda: self.system.FindVideoWithActivityandProp(
                args["a"], args["p"], args["z"]
            ),
            "FindVideoWithObjectandProp": lambda: self.system.FindVideoWithObjectandProp(
                args["o"], args["p"], args["z"]
            ),
            "FindObjectsInVideo": lambda: self.system.FindObjectsInVideo(args["v"], int(args["s"]), int(args["e"])),
            "FindActivitiesInVideo": lambda: self.system.FindActivitiesInVideo(args["v"], int(args["s"]), int(args["e"])),
            "FindActivitiesAndPropsinVideo": lambda: self.system.FindActivitiesAndPropsinVideo(
                args["v"], int(args["s"]), int(args["e"])
            ),
            "FindObjectsAndPropsinVideo": lambda: self.system.FindObjectsAndPropsinVideo(
                args["v"], int(args["s"]), int(args["e"])
            ),
            "DemonstrateAccess": lambda: self.system.demonstrate_access(args["v"], int(args["s"]), int(args["e"])),
        }
        return methods[name]()

    def _run_combined_query(self) -> None:
        try:
            conditions: List[Dict[str, Any]] = []
            for index, row in enumerate(self.combine_rows):
                item = {
                    "query_name": row["query_var"].get(),
                    "params": {key: value.get().strip() for key, value in row["param_vars"].items()},
                }
                if index > 0:
                    item["operator"] = row["operator_var"].get()
                conditions.append(item)

            result = self.system.evaluate_video_conditions(conditions)
            self._render_combined_result(conditions, result)
        except Exception as error:
            self.output.delete("1.0", tk.END)
            self.output.insert(tk.END, f"Lỗi: {error}")

    def _render_result(self, result: QueryResult) -> None:
        lines: List[str] = [f"Kết quả: {result.values}", "", "Matched segments:"]
        for record in result.matched_records:
            lines.append(
                f"- segment {record.segment_id} | {record.video_id} | "
                f"[{record.start_frame}, {record.end_frame}] | "
                f"object={record.object_name} {record.object_props} | "
                f"activity={record.activity_name} {record.activity_props}"
            )
        if result.access_trace:
            lines.extend(["", "Dấu vết truy cập:"])
            for entry in result.access_trace:
                lines.append(
                    f"- {entry.node_id} | {entry.video_id} | "
                    f"[{entry.start_frame}, {entry.end_frame}] | "
                    f"{'leaf' if entry.is_leaf else 'internal'} | "
                    f"{'visit' if entry.accepted else 'skip'}"
                )
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, "\n".join(lines))

    def _render_combined_result(self, conditions: List[Dict[str, Any]], result: QueryResult) -> None:
        lines: List[str] = ["Kết hợp truy vấn:"]
        for index, condition in enumerate(conditions):
            prefix = condition.get("operator", "START")
            lines.append(f"- {prefix} {condition['query_name']} {condition['params']}")
        lines.extend(["", f"Kết quả cuối: {result.values}", "", "Matched segments:"])
        for record in result.matched_records:
            lines.append(
                f"- segment {record.segment_id} | {record.video_id} | "
                f"[{record.start_frame}, {record.end_frame}] | "
                f"object={record.object_name} {record.object_props} | "
                f"activity={record.activity_name} {record.activity_props}"
            )
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, "\n".join(lines))


def main() -> None:
    root = tk.Tk()
    app = Chapter7App(root, build_demo_system())
    root.mainloop()


if __name__ == "__main__":
    main()
