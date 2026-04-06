from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple


@dataclass(frozen=True)
class SegmentRecord:
    segment_id: int
    video_id: str
    start_frame: int
    end_frame: int
    object_name: str
    activity_name: str
    object_props: Dict[str, str]
    activity_props: Dict[str, str]

    def __post_init__(self) -> None:
        if self.start_frame > self.end_frame:
            raise ValueError("Yêu cầu start_frame <= end_frame.")

    def overlaps_closed(self, start_frame: int, end_frame: int) -> bool:
        return self.start_frame <= end_frame and self.end_frame >= start_frame

    def triple(self) -> tuple[str, int, int]:
        return (self.video_id, self.start_frame, self.end_frame)


@dataclass
class ObjectArrayEntry:
    video_id: str
    object_name: str
    ptrs: List[str] = field(default_factory=list)
    record_indices: List[int] = field(default_factory=list)


@dataclass
class ActivityArrayEntry:
    video_id: str
    activity_name: str
    ptrs: List[str] = field(default_factory=list)
    record_indices: List[int] = field(default_factory=list)


@dataclass
class PropArrayEntry:
    video_id: str
    owner_name: str
    prop_name: str
    prop_value: str
    ptrs: List[str] = field(default_factory=list)
    record_indices: List[int] = field(default_factory=list)


@dataclass
class RSNode:
    node_id: str
    video_id: str
    start_frame: int
    end_frame: int
    children: List["RSNode"] = field(default_factory=list)
    record_indices: List[int] = field(default_factory=list)
    object_ptrs: List[int] = field(default_factory=list)
    activity_ptrs: List[int] = field(default_factory=list)
    object_prop_ptrs: List[int] = field(default_factory=list)
    activity_prop_ptrs: List[int] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def overlaps(self, start_frame: int, end_frame: int) -> bool:
        return self.start_frame <= end_frame and self.end_frame >= start_frame


@dataclass(frozen=True)
class AccessTraceEntry:
    node_id: str
    video_id: str
    start_frame: int
    end_frame: int
    is_leaf: bool
    accepted: bool


@dataclass(frozen=True)
class QueryResult:
    values: List[Any]
    matched_records: List[SegmentRecord]
    access_trace: List[AccessTraceEntry]


class VideoRSTree:
    def __init__(
        self,
        video_id: str,
        root: RSNode,
        records: List[SegmentRecord],
        max_entries: int = 4,
        node_counter: int = 1,
    ):
        self.video_id = video_id
        self.root = root
        self.records = records
        self.max_entries = max_entries
        self.node_counter = node_counter

    @classmethod
    def build(
        cls,
        video_id: str,
        record_pairs: Sequence[tuple[int, SegmentRecord]],
        records: List[SegmentRecord],
        max_entries: int = 4,
    ) -> "VideoRSTree":
        # Kiểm tra điều kiện tối thiểu để tạo cây.
        if max_entries < 2:
            raise ValueError("Yêu cầu max_entries >= 2.")
        if not record_pairs:
            raise ValueError("Không thể tạo RS-tree từ tập rỗng.")

        # Bước 1: sắp xếp các segment theo thời gian.
        sorted_pairs = sorted(
            record_pairs,
            key=lambda item: (item[1].start_frame, item[1].end_frame, item[1].segment_id),
        )
        # Bước 2: chia segment đã sắp xếp thành từng nhóm nhỏ để tạo leaf node.
        leaves: List[RSNode] = []
        for leaf_index, chunk_start in enumerate(range(0, len(sorted_pairs), max_entries), start=1):
            chunk = sorted_pairs[chunk_start : chunk_start + max_entries]
            leaves.append(
                RSNode(
                    node_id=f"{video_id}-L{leaf_index}",
                    video_id=video_id,
                    # Khoảng frame của leaf là khung bao tất cả record trong nhóm.
                    start_frame=min(record.start_frame for _, record in chunk),
                    end_frame=max(record.end_frame for _, record in chunk),
                    # Leaf giữ chỉ số của các record gốc.
                    record_indices=[index for index, _ in chunk],
                )
            )

        # Bước 3: gom các leaf thành từng tầng internal node từ dưới lên trên.
        level = leaves
        depth = 1
        while len(level) > 1:
            next_level: List[RSNode] = []
            for group_index, chunk_start in enumerate(range(0, len(level), max_entries), start=1):
                chunk = level[chunk_start : chunk_start + max_entries]
                next_level.append(
                    RSNode(
                        node_id=f"{video_id}-N{depth}-{group_index}",
                        video_id=video_id,
                        # Internal node lấy khung bao frame của tất cả node con.
                        start_frame=min(node.start_frame for node in chunk),
                        end_frame=max(node.end_frame for node in chunk),
                        # Internal node không giữ record trực tiếp, mà giữ danh sách con.
                        children=chunk,
                    )
                )
            # Chuyển lên tầng vừa tạo và tiếp tục gom cho đến khi còn 1 node.
            level = next_level
            depth += 1

        # Node cuối cùng là gốc tạm thời của cây.
        root = level[0]
        if root.node_id.endswith("ROOT"):
            return cls(video_id, root, records, max_entries=max_entries, node_counter=len(level) + 1)
        # Bước 4: bọc node gốc tạm thời thành ROOT chính thức của video.
        root = RSNode(
            node_id=f"{video_id}-ROOT",
            video_id=video_id,
            start_frame=root.start_frame,
            end_frame=root.end_frame,
            children=root.children if not root.is_leaf else [root],
        )
        # Hoàn tất object cây và khởi tạo bộ đếm node cho các lần chèn sau.
        tree = cls(video_id, root, records, max_entries=max_entries)
        tree.node_counter = tree._count_nodes(tree.root) + 1
        return tree

    def query_range(self, start_frame: int, end_frame: int) -> tuple[Set[int], List[AccessTraceEntry]]:
        # Cửa vào truy vấn theo frame range trên RS-tree của một video.
        matched_indices: Set[int] = set()
        trace: List[AccessTraceEntry] = []
        # Bắt đầu duyệt cây từ root.
        self._query_node(self.root, start_frame, end_frame, matched_indices, trace)
        return matched_indices, trace

    def insert(self, record_index: int) -> None:
        # Điểm vào để chèn động một record vào RS-tree của một video.
        record = self.records[record_index]
        split_node = self._insert_into_node(self.root, record_index)
        if split_node is not None:
            if self.root.node_id.endswith("ROOT"):
                self.root.node_id = self._new_node_id("N")
            self.root = RSNode(
                node_id=f"{self.video_id}-ROOT",
                video_id=self.video_id,
                start_frame=min(self.root.start_frame, split_node.start_frame),
                end_frame=max(self.root.end_frame, split_node.end_frame),
                children=[self.root, split_node],
            )
        self._refresh_node_bounds(self.root)

    def _query_node(
        self,
        node: RSNode,
        start_frame: int,
        end_frame: int,
        matched_indices: Set[int],
        trace: List[AccessTraceEntry],
    ) -> None:
        # Kiểm tra node hiện tại có giao với khoảng frame cần truy vấn hay không.
        accepted = node.overlaps(start_frame, end_frame)
        trace.append(
            AccessTraceEntry(
                node_id=node.node_id,
                video_id=node.video_id,
                start_frame=node.start_frame,
                end_frame=node.end_frame,
                is_leaf=node.is_leaf,
                accepted=accepted,
            )
        )
        if not accepted:
            return
        if node.is_leaf:
            matched_indices.update(node.record_indices)
            return
        for child in node.children:
            self._query_node(child, start_frame, end_frame, matched_indices, trace)

    def _insert_into_node(self, node: RSNode, record_index: int) -> RSNode | None:
        record = self.records[record_index]
        if node.is_leaf:
            # Chèn trực tiếp vào leaf phù hợp; nếu vượt sức chứa thì tách node.
            node.record_indices.append(record_index)
            self._refresh_node_bounds(node)
            if len(node.record_indices) > self.max_entries:
                return self._split_leaf(node)
            return None

        # Chọn node con làm tăng khoảng bao phủ ít nhất.
        target_child = min(
            node.children,
            key=lambda child: (self._interval_enlargement(child, record), child.start_frame, child.end_frame),
        )
        split_child = self._insert_into_node(target_child, record_index)
        if split_child is not None:
            # Nếu node con bị tách, node hiện tại nhận thêm sibling mới.
            node.children.append(split_child)
        self._refresh_node_bounds(node)
        if len(node.children) > self.max_entries:
            return self._split_internal(node)
        return None

    def _split_leaf(self, node: RSNode) -> RSNode:
        # Tách một leaf bị tràn thành hai leaf theo thứ tự các record.
        ordered = sorted(
            node.record_indices,
            key=lambda index: (
                self.records[index].start_frame,
                self.records[index].end_frame,
                self.records[index].segment_id,
            ),
        )
        midpoint = len(ordered) // 2
        node.record_indices = ordered[:midpoint]
        sibling = RSNode(
            node_id=self._new_node_id("L"),
            video_id=self.video_id,
            start_frame=0,
            end_frame=0,
            record_indices=ordered[midpoint:],
        )
        self._refresh_node_bounds(node)
        self._refresh_node_bounds(sibling)
        return sibling

    def _split_internal(self, node: RSNode) -> RSNode:
        # Tách một internal node bị tràn thành hai node anh em.
        ordered_children = sorted(
            node.children,
            key=lambda child: (child.start_frame, child.end_frame, child.node_id),
        )
        midpoint = len(ordered_children) // 2
        node.children = ordered_children[:midpoint]
        sibling = RSNode(
            node_id=self._new_node_id("N"),
            video_id=self.video_id,
            start_frame=0,
            end_frame=0,
            children=ordered_children[midpoint:],
        )
        self._refresh_node_bounds(node)
        self._refresh_node_bounds(sibling)
        return sibling

    def _refresh_node_bounds(self, node: RSNode) -> None:
        if node.is_leaf:
            records = [self.records[index] for index in node.record_indices]
            node.start_frame = min(record.start_frame for record in records)
            node.end_frame = max(record.end_frame for record in records)
            return
        node.start_frame = min(child.start_frame for child in node.children)
        node.end_frame = max(child.end_frame for child in node.children)

    def _interval_enlargement(self, node: RSNode, record: SegmentRecord) -> int:
        new_start = min(node.start_frame, record.start_frame)
        new_end = max(node.end_frame, record.end_frame)
        return (new_end - new_start) - (node.end_frame - node.start_frame)

    def _new_node_id(self, prefix: str) -> str:
        node_id = f"{self.video_id}-{prefix}{self.node_counter}"
        self.node_counter += 1
        return node_id

    def _count_nodes(self, node: RSNode) -> int:
        return 1 + sum(self._count_nodes(child) for child in node.children)


class VideoSegmentSystem:
    def __init__(
        self,
        segment_table: List[SegmentRecord],
        object_array: List[ObjectArrayEntry],
        activity_array: List[ActivityArrayEntry],
        object_prop_array: List[PropArrayEntry],
        activity_prop_array: List[PropArrayEntry],
        rs_trees: Dict[str, VideoRSTree],
        max_entries: int,
        object_index: Dict[tuple[str, str], int],
        activity_index: Dict[tuple[str, str], int],
        object_prop_index: Dict[tuple[str, str, str, str], int],
        activity_prop_index: Dict[tuple[str, str, str, str], int],
    ):
        self.segment_table = segment_table
        self.object_array = object_array
        self.activity_array = activity_array
        self.object_prop_array = object_prop_array
        self.activity_prop_array = activity_prop_array
        self.rs_trees = rs_trees
        self.frame_segment_trees = rs_trees
        self.max_entries = max_entries
        self.object_index = object_index
        self.activity_index = activity_index
        self.object_prop_index = object_prop_index
        self.activity_prop_index = activity_prop_index

    @classmethod
    def from_segment_table(
        cls,
        segment_table: Iterable[Dict[str, Any]],
        max_entries: int = 4,
    ) -> "VideoSegmentSystem":
        records = [cls._parse_row(row) for row in segment_table]
        object_array: List[ObjectArrayEntry] = []
        activity_array: List[ActivityArrayEntry] = []
        object_prop_array: List[PropArrayEntry] = []
        activity_prop_array: List[PropArrayEntry] = []
        object_index: Dict[tuple[str, str], int] = {}
        activity_index: Dict[tuple[str, str], int] = {}
        object_prop_index: Dict[tuple[str, str, str, str], int] = {}
        activity_prop_index: Dict[tuple[str, str, str, str], int] = {}

        grouped_records: Dict[str, List[tuple[int, SegmentRecord]]] = {}
        for record_index, record in enumerate(records):
            grouped_records.setdefault(record.video_id, []).append((record_index, record))

            object_key = (record.video_id, record.object_name)
            if object_key not in object_index:
                object_index[object_key] = len(object_array)
                object_array.append(ObjectArrayEntry(record.video_id, record.object_name))
            object_ptr = object_index[object_key]
            object_array[object_ptr].record_indices.append(record_index)

            activity_key = (record.video_id, record.activity_name)
            if activity_key not in activity_index:
                activity_index[activity_key] = len(activity_array)
                activity_array.append(ActivityArrayEntry(record.video_id, record.activity_name))
            activity_ptr = activity_index[activity_key]
            activity_array[activity_ptr].record_indices.append(record_index)

            for prop_name, prop_value in record.object_props.items():
                object_prop_key = (record.video_id, record.object_name, prop_name, prop_value)
                if object_prop_key not in object_prop_index:
                    object_prop_index[object_prop_key] = len(object_prop_array)
                    object_prop_array.append(
                        PropArrayEntry(record.video_id, record.object_name, prop_name, prop_value)
                    )
                object_prop_ptr = object_prop_index[object_prop_key]
                object_prop_array[object_prop_ptr].record_indices.append(record_index)

            for prop_name, prop_value in record.activity_props.items():
                activity_prop_key = (record.video_id, record.activity_name, prop_name, prop_value)
                if activity_prop_key not in activity_prop_index:
                    activity_prop_index[activity_prop_key] = len(activity_prop_array)
                    activity_prop_array.append(
                        PropArrayEntry(record.video_id, record.activity_name, prop_name, prop_value)
                    )
                activity_prop_ptr = activity_prop_index[activity_prop_key]
                activity_prop_array[activity_prop_ptr].record_indices.append(record_index)

        rs_trees = {
            video_id: VideoRSTree.build(video_id, pairs, records, max_entries=max_entries)
            for video_id, pairs in grouped_records.items()
        }

        for node in (tree.root for tree in rs_trees.values()):
            cls._attach_ptrs(
                node,
                records,
                object_index,
                activity_index,
                object_prop_index,
                activity_prop_index,
            )
            cls._collect_ptrs(
                node,
                object_array,
                activity_array,
                object_prop_array,
                activity_prop_array,
            )

        return cls(
            records,
            object_array,
            activity_array,
            object_prop_array,
            activity_prop_array,
            rs_trees,
            max_entries,
            object_index,
            activity_index,
            object_prop_index,
            activity_prop_index,
        )

    @classmethod
    def load_json(cls, path: str, max_entries: int = 4) -> "VideoSegmentSystem":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_segment_table(payload, max_entries=max_entries)

    def add_segment(self, row: Dict[str, Any]) -> SegmentRecord:
        # Chèn mới ở mức hệ thống: thêm segment, cập nhật chỉ mục và cập nhật cây.
        record = self._parse_row(row)
        record_index = len(self.segment_table)
        self.segment_table.append(record)

        self._register_record_indices(record_index, record)

        tree = self.rs_trees.get(record.video_id)
        if tree is None:
            tree = VideoRSTree.build(
                record.video_id,
                [(record_index, record)],
                self.segment_table,
                max_entries=self.max_entries,
            )
            self.rs_trees[record.video_id] = tree
            self.frame_segment_trees = self.rs_trees
        else:
            tree.insert(record_index)

        self._rebuild_tree_ptrs()
        return record

    @staticmethod
    def _parse_row(row: Dict[str, Any]) -> SegmentRecord:
        object_props = row.get("object_props")
        activity_props = row.get("activity_props")
        if object_props is None:
            object_props = {}
            if "prop_name" in row:
                object_props["item"] = str(row["prop_name"]).lower()
            if "zone" in row:
                object_props["location"] = str(row["zone"]).lower()
        if activity_props is None:
            activity_props = {}
            if "prop_name" in row:
                activity_props["item"] = str(row["prop_name"]).lower()
            if "zone" in row:
                activity_props["location"] = str(row["zone"]).lower()

        return SegmentRecord(
            segment_id=int(row["segment_id"]),
            video_id=str(row["video_id"]),
            start_frame=int(row["start_frame"]),
            end_frame=int(row["end_frame"]),
            object_name=str(row["object_name"]).lower(),
            activity_name=str(row.get("activity_name", row.get("activity", ""))).lower(),
            object_props={str(key).lower(): str(value).lower() for key, value in dict(object_props).items()},
            activity_props={str(key).lower(): str(value).lower() for key, value in dict(activity_props).items()},
        )

    def _register_record_indices(self, record_index: int, record: SegmentRecord) -> None:
        object_key = (record.video_id, record.object_name)
        if object_key not in self.object_index:
            self.object_index[object_key] = len(self.object_array)
            self.object_array.append(ObjectArrayEntry(record.video_id, record.object_name))
        self.object_array[self.object_index[object_key]].record_indices.append(record_index)

        activity_key = (record.video_id, record.activity_name)
        if activity_key not in self.activity_index:
            self.activity_index[activity_key] = len(self.activity_array)
            self.activity_array.append(ActivityArrayEntry(record.video_id, record.activity_name))
        self.activity_array[self.activity_index[activity_key]].record_indices.append(record_index)

        for prop_name, prop_value in record.object_props.items():
            object_prop_key = (record.video_id, record.object_name, prop_name, prop_value)
            if object_prop_key not in self.object_prop_index:
                self.object_prop_index[object_prop_key] = len(self.object_prop_array)
                self.object_prop_array.append(
                    PropArrayEntry(record.video_id, record.object_name, prop_name, prop_value)
                )
            self.object_prop_array[self.object_prop_index[object_prop_key]].record_indices.append(record_index)

        for prop_name, prop_value in record.activity_props.items():
            activity_prop_key = (record.video_id, record.activity_name, prop_name, prop_value)
            if activity_prop_key not in self.activity_prop_index:
                self.activity_prop_index[activity_prop_key] = len(self.activity_prop_array)
                self.activity_prop_array.append(
                    PropArrayEntry(record.video_id, record.activity_name, prop_name, prop_value)
                )
            self.activity_prop_array[self.activity_prop_index[activity_prop_key]].record_indices.append(record_index)

    def _rebuild_tree_ptrs(self) -> None:
        # Cập nhật lại các con trỏ từ node đến các bảng chỉ mục sau khi cây thay đổi.
        for entry in self.object_array:
            entry.ptrs.clear()
        for entry in self.activity_array:
            entry.ptrs.clear()
        for entry in self.object_prop_array:
            entry.ptrs.clear()
        for entry in self.activity_prop_array:
            entry.ptrs.clear()

        for tree in self.rs_trees.values():
            tree.records = self.segment_table
            self._attach_ptrs(
                tree.root,
                self.segment_table,
                self.object_index,
                self.activity_index,
                self.object_prop_index,
                self.activity_prop_index,
            )
            self._collect_ptrs(
                tree.root,
                self.object_array,
                self.activity_array,
                self.object_prop_array,
                self.activity_prop_array,
            )

    @classmethod
    def _attach_ptrs(
        cls,
        node: RSNode,
        records: List[SegmentRecord],
        object_index: Dict[tuple[str, str], int],
        activity_index: Dict[tuple[str, str], int],
        object_prop_index: Dict[tuple[str, str, str, str], int],
        activity_prop_index: Dict[tuple[str, str, str, str], int],
    ) -> tuple[Set[int], Set[int], Set[int], Set[int]]:
        object_ptrs: Set[int] = set()
        activity_ptrs: Set[int] = set()
        object_prop_ptrs: Set[int] = set()
        activity_prop_ptrs: Set[int] = set()

        if node.is_leaf:
            for record_index in node.record_indices:
                record = records[record_index]
                object_ptrs.add(object_index[(record.video_id, record.object_name)])
                activity_ptrs.add(activity_index[(record.video_id, record.activity_name)])
                for prop_name, prop_value in record.object_props.items():
                    object_prop_ptrs.add(
                        object_prop_index[(record.video_id, record.object_name, prop_name, prop_value)]
                    )
                for prop_name, prop_value in record.activity_props.items():
                    activity_prop_ptrs.add(
                        activity_prop_index[(record.video_id, record.activity_name, prop_name, prop_value)]
                    )
        else:
            for child in node.children:
                (
                    child_object_ptrs,
                    child_activity_ptrs,
                    child_object_prop_ptrs,
                    child_activity_prop_ptrs,
                ) = cls._attach_ptrs(
                    child,
                    records,
                    object_index,
                    activity_index,
                    object_prop_index,
                    activity_prop_index,
                )
                object_ptrs.update(child_object_ptrs)
                activity_ptrs.update(child_activity_ptrs)
                object_prop_ptrs.update(child_object_prop_ptrs)
                activity_prop_ptrs.update(child_activity_prop_ptrs)

        node.object_ptrs = sorted(object_ptrs)
        node.activity_ptrs = sorted(activity_ptrs)
        node.object_prop_ptrs = sorted(object_prop_ptrs)
        node.activity_prop_ptrs = sorted(activity_prop_ptrs)
        return object_ptrs, activity_ptrs, object_prop_ptrs, activity_prop_ptrs

    @classmethod
    def _collect_ptrs(
        cls,
        node: RSNode,
        object_array: List[ObjectArrayEntry],
        activity_array: List[ActivityArrayEntry],
        object_prop_array: List[PropArrayEntry],
        activity_prop_array: List[PropArrayEntry],
    ) -> None:
        for ptr in node.object_ptrs:
            if node.node_id not in object_array[ptr].ptrs:
                object_array[ptr].ptrs.append(node.node_id)
        for ptr in node.activity_ptrs:
            if node.node_id not in activity_array[ptr].ptrs:
                activity_array[ptr].ptrs.append(node.node_id)
        for ptr in node.object_prop_ptrs:
            if node.node_id not in object_prop_array[ptr].ptrs:
                object_prop_array[ptr].ptrs.append(node.node_id)
        for ptr in node.activity_prop_ptrs:
            if node.node_id not in activity_prop_array[ptr].ptrs:
                activity_prop_array[ptr].ptrs.append(node.node_id)
        for child in node.children:
            cls._collect_ptrs(
                child,
                object_array,
                activity_array,
                object_prop_array,
                activity_prop_array,
            )

    def export_json(self) -> Dict[str, Any]:
        return {
            "segment_table": [asdict(record) for record in self.segment_table],
            "object_array": [asdict(entry) for entry in self.object_array],
            "activity_array": [asdict(entry) for entry in self.activity_array],
            "object_prop_array": [asdict(entry) for entry in self.object_prop_array],
            "activity_prop_array": [asdict(entry) for entry in self.activity_prop_array],
            "rs_trees": {
                video_id: self._serialize_node(tree.root)
                for video_id, tree in self.rs_trees.items()
            },
        }

    def _serialize_node(self, node: RSNode) -> Dict[str, Any]:
        return {
            "node_id": node.node_id,
            "video_id": node.video_id,
            "start_frame": node.start_frame,
            "end_frame": node.end_frame,
            "is_leaf": node.is_leaf,
            "record_indices": node.record_indices,
            "object_ptrs": node.object_ptrs,
            "activity_ptrs": node.activity_ptrs,
            "object_prop_ptrs": node.object_prop_ptrs,
            "activity_prop_ptrs": node.activity_prop_ptrs,
            "children": [self._serialize_node(child) for child in node.children],
        }

    def FindVideoWithObject(self, o: str) -> QueryResult:
        matched_indices: Set[int] = set()
        for entry in self.object_array:
            if entry.object_name == o.lower():
                matched_indices.update(entry.record_indices)
        matched_records = self._records_from_indices(matched_indices)
        return QueryResult(self._triples_from_records(matched_records), matched_records, [])

    def FindVideoWithActivity(self, a: str) -> QueryResult:
        matched_indices: Set[int] = set()
        for entry in self.activity_array:
            if entry.activity_name == a.lower():
                matched_indices.update(entry.record_indices)
        matched_records = self._records_from_indices(matched_indices)
        return QueryResult(self._triples_from_records(matched_records), matched_records, [])

    def FindVideoWithActivityandProp(self, a: str, p: str, z: str) -> QueryResult:
        matched_indices: Set[int] = set()
        for entry in self.activity_prop_array:
            if (
                entry.owner_name == a.lower()
                and entry.prop_name == p.lower()
                and entry.prop_value == z.lower()
            ):
                matched_indices.update(entry.record_indices)
        matched_records = self._records_from_indices(matched_indices)
        return QueryResult(self._triples_from_records(matched_records), matched_records, [])

    def FindVideoWithObjectandProp(self, o: str, p: str, z: str) -> QueryResult:
        matched_indices: Set[int] = set()
        for entry in self.object_prop_array:
            if (
                entry.owner_name == o.lower()
                and entry.prop_name == p.lower()
                and entry.prop_value == z.lower()
            ):
                matched_indices.update(entry.record_indices)
        matched_records = self._records_from_indices(matched_indices)
        return QueryResult(self._triples_from_records(matched_records), matched_records, [])

    def FindObjectsInVideo(self, v: str, s: int, e: int) -> QueryResult:
        # Truy vấn frame range trên cây của video v, rồi rút ra tập object xuất hiện.
        matched_records, trace = self._query_video_range(v, s, e)
        return QueryResult(sorted({record.object_name for record in matched_records}), matched_records, trace)

    def FindActivitiesInVideo(self, v: str, s: int, e: int) -> QueryResult:
        # Truy vấn frame range trên cây của video v, rồi rút ra tập activity xuất hiện.
        matched_records, trace = self._query_video_range(v, s, e)
        return QueryResult(sorted({record.activity_name for record in matched_records}), matched_records, trace)

    def FindActivitiesAndPropsinVideo(self, v: str, s: int, e: int) -> QueryResult:
        # Đi trên RS-tree trước, sau đó lấy activity và các thuộc tính activity của các record khớp.
        matched_records, trace = self._query_video_range(v, s, e)
        values = sorted(
            {
                (record.activity_name, key, value)
                for record in matched_records
                for key, value in sorted(record.activity_props.items())
            }
        )
        return QueryResult(values, matched_records, trace)

    def FindObjectsAndPropsinVideo(self, v: str, s: int, e: int) -> QueryResult:
        # Đi trên RS-tree trước, sau đó lấy object và các thuộc tính object của các record khớp.
        matched_records, trace = self._query_video_range(v, s, e)
        values = sorted(
            {
                (record.object_name, key, value)
                for record in matched_records
                for key, value in sorted(record.object_props.items())
            }
        )
        return QueryResult(values, matched_records, trace)

    def demonstrate_access(self, v: str, s: int, e: int) -> QueryResult:
        matched_records, trace = self._query_video_range(v, s, e)
        values = [
            f"{record.segment_id}:{record.video_id}[{record.start_frame},{record.end_frame}]"
            for record in matched_records
        ]
        return QueryResult(values, matched_records, trace)

    def run_video_query(self, query_name: str, **kwargs: str) -> QueryResult:
        methods = {
            "FindVideoWithObject": lambda: self.FindVideoWithObject(kwargs["o"]),
            "FindVideoWithActivity": lambda: self.FindVideoWithActivity(kwargs["a"]),
            "FindVideoWithActivityandProp": lambda: self.FindVideoWithActivityandProp(
                kwargs["a"], kwargs["p"], kwargs["z"]
            ),
            "FindVideoWithObjectandProp": lambda: self.FindVideoWithObjectandProp(
                kwargs["o"], kwargs["p"], kwargs["z"]
            ),
        }
        if query_name not in methods:
            raise ValueError(f"Hàm {query_name} không hỗ trợ trong chế độ kết hợp.")
        return methods[query_name]()

    def combine_video_results(
        self,
        left_result: QueryResult,
        operator: str,
        right_result: QueryResult,
    ) -> QueryResult:
        left_videos = self._video_ids_from_result(left_result)
        right_videos = self._video_ids_from_result(right_result)

        if operator == "AND":
            selected_videos = left_videos & right_videos
        elif operator == "OR":
            selected_videos = left_videos | right_videos
        elif operator == "NOT":
            selected_videos = left_videos - right_videos
        else:
            raise ValueError("Toán tử phải là AND, OR hoặc NOT.")

        matched_records = self._records_for_videos(selected_videos)
        return QueryResult(sorted(selected_videos), matched_records, [])

    def evaluate_video_conditions(self, conditions: List[Dict[str, Any]]) -> QueryResult:
        if not conditions:
            raise ValueError("Cần ít nhất một điều kiện.")

        first = conditions[0]
        result = self.run_video_query(first["query_name"], **first["params"])
        for condition in conditions[1:]:
            next_result = self.run_video_query(condition["query_name"], **condition["params"])
            result = self.combine_video_results(result, condition["operator"], next_result)
        return result

    def _query_video_range(
        self,
        video_id: str,
        start_frame: int,
        end_frame: int,
    ) -> tuple[List[SegmentRecord], List[AccessTraceEntry]]:
        # Chọn đúng RS-tree của video đang được hỏi.
        tree = self.rs_trees.get(video_id)
        if tree is None:
            return [], []
        # Dùng cây để lấy các record có khoảng frame giao với truy vấn.
        matched_indices, trace = tree.query_range(start_frame, end_frame)
        matched_records = [
            self.segment_table[index]
            for index in sorted(matched_indices, key=lambda idx: self.segment_table[idx].segment_id)
            if self.segment_table[index].overlaps_closed(start_frame, end_frame)
        ]
        return matched_records, trace

    def _records_from_indices(self, indices: Set[int]) -> List[SegmentRecord]:
        return [
            self.segment_table[index]
            for index in sorted(indices, key=lambda idx: self.segment_table[idx].segment_id)
        ]

    def _video_ids_from_result(self, result: QueryResult) -> Set[str]:
        return {record.video_id for record in result.matched_records}

    def _records_for_videos(self, video_ids: Set[str]) -> List[SegmentRecord]:
        return [record for record in self.segment_table if record.video_id in video_ids]

    def _triples_from_records(self, records: List[SegmentRecord]) -> List[Tuple[str, int, int]]:
        seen: Set[Tuple[str, int, int]] = set()
        triples: List[Tuple[str, int, int]] = []
        for record in records:
            triple = record.triple()
            if triple not in seen:
                seen.add(triple)
                triples.append(triple)
        return triples


def build_demo_segment_table() -> List[Dict[str, Any]]:
    return [
        {"segment_id": 1, "video_id": "demo_video_01", "start_frame": 1, "end_frame": 12, "object_name": "person", "activity_name": "walking", "object_props": {"item": "bag", "location": "street"}, "activity_props": {"item": "bag", "location": "street"}},
        {"segment_id": 2, "video_id": "demo_video_01", "start_frame": 13, "end_frame": 24, "object_name": "person", "activity_name": "running", "object_props": {"item": "ball", "location": "park"}, "activity_props": {"item": "ball", "location": "park"}},
        {"segment_id": 3, "video_id": "demo_video_01", "start_frame": 25, "end_frame": 36, "object_name": "dog", "activity_name": "running", "object_props": {"item": "ball", "location": "park"}, "activity_props": {"item": "ball", "location": "park"}},
        {"segment_id": 4, "video_id": "demo_video_01", "start_frame": 37, "end_frame": 48, "object_name": "person", "activity_name": "throwing", "object_props": {"item": "ball", "location": "park"}, "activity_props": {"item": "ball", "location": "park"}},
        {"segment_id": 5, "video_id": "demo_video_01", "start_frame": 49, "end_frame": 60, "object_name": "bicycle", "activity_name": "moving", "object_props": {"surface": "road", "location": "street"}, "activity_props": {"surface": "road", "location": "street"}},
        {"segment_id": 6, "video_id": "demo_video_01", "start_frame": 61, "end_frame": 72, "object_name": "person", "activity_name": "talking", "object_props": {"device": "phone", "location": "sidewalk"}, "activity_props": {"device": "phone", "location": "sidewalk"}},
        {"segment_id": 7, "video_id": "demo_video_01", "start_frame": 73, "end_frame": 84, "object_name": "car", "activity_name": "moving", "object_props": {"surface": "road", "location": "street"}, "activity_props": {"surface": "road", "location": "street"}},
        {"segment_id": 8, "video_id": "demo_video_01", "start_frame": 85, "end_frame": 100, "object_name": "person", "activity_name": "standing", "object_props": {"item": "umbrella", "location": "street"}, "activity_props": {"item": "umbrella", "location": "street"}},
        {"segment_id": 9, "video_id": "demo_video_02", "start_frame": 1, "end_frame": 18, "object_name": "car", "activity_name": "moving", "object_props": {"surface": "road", "location": "street"}, "activity_props": {"surface": "road", "location": "street"}},
        {"segment_id": 10, "video_id": "demo_video_02", "start_frame": 19, "end_frame": 35, "object_name": "person", "activity_name": "driving", "object_props": {"vehicle": "car", "location": "street"}, "activity_props": {"vehicle": "car", "location": "street"}},
        {"segment_id": 11, "video_id": "demo_video_02", "start_frame": 36, "end_frame": 55, "object_name": "person", "activity_name": "parking", "object_props": {"vehicle": "car", "location": "garage"}, "activity_props": {"vehicle": "car", "location": "garage"}},
        {"segment_id": 12, "video_id": "demo_video_02", "start_frame": 56, "end_frame": 90, "object_name": "person", "activity_name": "walking", "object_props": {"item": "bag", "location": "garage"}, "activity_props": {"item": "bag", "location": "garage"}},
    ]


def build_demo_system(max_entries: int = 4) -> VideoSegmentSystem:
    sample_path = Path(__file__).with_name("chapter7_sample_segments.json")
    if sample_path.exists():
        return VideoSegmentSystem.load_json(str(sample_path), max_entries=max_entries)
    return VideoSegmentSystem.from_segment_table(build_demo_segment_table(), max_entries=max_entries)


def print_query_result(title: str, result: QueryResult) -> None:
    print(f"\n=== {title} ===")
    print("Kết quả:", result.values)
    print("Matched segments:")
    for record in result.matched_records:
        print(
            f"- segment {record.segment_id} | {record.video_id} | "
            f"[{record.start_frame}, {record.end_frame}] | "
            f"object={record.object_name} {record.object_props} | "
            f"activity={record.activity_name} {record.activity_props}"
        )
    if result.access_trace:
        print("Access trace:")
        for entry in result.access_trace:
            verdict = "visit" if entry.accepted else "skip"
            node_type = "leaf" if entry.is_leaf else "internal"
            print(
                f"- node {entry.node_id} ({node_type}) {entry.video_id} "
                f"[{entry.start_frame}, {entry.end_frame}] -> {verdict}"
            )


def main() -> None:
    system = build_demo_system()
    print_query_result("FindVideoWithObject(person)", system.FindVideoWithObject("person"))
    print_query_result("FindVideoWithActivity(running)", system.FindVideoWithActivity("running"))
    print_query_result(
        "FindVideoWithActivityandProp(running, location, park)",
        system.FindVideoWithActivityandProp("running", "location", "park"),
    )
    print_query_result(
        "FindVideoWithObjectandProp(person, item, bag)",
        system.FindVideoWithObjectandProp("person", "item", "bag"),
    )
    print_query_result(
        "FindObjectsInVideo(demo_video_01, 20, 80)",
        system.FindObjectsInVideo("demo_video_01", 20, 80),
    )
    print_query_result(
        "Demonstrate access for demo_video_01 [20, 80]",
        system.demonstrate_access("demo_video_01", 20, 80),
    )


FrameSegmentNode = RSNode
VideoFrameSegmentTree = VideoRSTree

__all__ = [
    "AccessTraceEntry",
    "ActivityArrayEntry",
    "FrameSegmentNode",
    "ObjectArrayEntry",
    "PropArrayEntry",
    "QueryResult",
    "RSNode",
    "SegmentRecord",
    "VideoFrameSegmentTree",
    "VideoRSTree",
    "VideoSegmentSystem",
    "build_demo_segment_table",
    "build_demo_system",
    "main",
    "print_query_result",
]
