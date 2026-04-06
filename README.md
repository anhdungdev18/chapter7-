# Chapter 7: Xây Dựng RS-tree Và Hệ Truy Vấn Video

## 1. Bài Toán

Chapter 7 giải bài toán lập chỉ mục và truy vấn trên dữ liệu video đã được phân đoạn theo frame.

Đầu vào:

- `segment table`
- thông tin `object`
- thông tin `activity`
- các thuộc tính `prop`

Mục tiêu:

- xây dựng `RS-tree`
- tạo `OBJECTARRAY`, `ACTIVITYARRAY`, `PROPARRAY`
- hỗ trợ các phép truy vấn trên video
- cung cấp GUI để demo

## 2. Ý Tưởng Chung

```text
Segment Table
    ->
RS-tree + OBJECTARRAY + ACTIVITYARRAY + PROPARRAY
    ->
Truy vấn theo object / activity / prop / frame range
```

Ý chính:

- dữ liệu gốc nằm trong `segment_table`
- cây dùng để chỉ mục theo khoảng frame
- các array dùng để chỉ mục theo nội dung

## 3. Biểu Diễn Dữ Liệu

Các thành phần chính trong code:

- `SegmentRecord`
  - lưu một đoạn video
- `RSNode`
  - nút của cây RS-tree
- `VideoRSTree`
  - cây của từng video
- `ObjectArrayEntry`
  - chỉ mục theo object
- `ActivityArrayEntry`
  - chỉ mục theo activity
- `PropArrayEntry`
  - chỉ mục theo thuộc tính
- `VideoSegmentSystem`
  - hệ thống chính quản lý toàn bộ dữ liệu và truy vấn

## 4. Dữ Liệu Gốc

Mỗi `SegmentRecord` lưu:

- `segment_id`
- `video_id`
- `start_frame`
- `end_frame`
- `object_name`
- `activity_name`
- `object_props`
- `activity_props`

Đây là bảng segment gốc của hệ thống.

## 5. Cấu Trúc RS-tree

Chapter 7 hiện dùng `RS-tree` 1 chiều theo trục frame.

Mỗi video có một cây riêng. Mỗi node lưu:

- `start_frame`, `end_frame`
- `children` nếu là node trong
- `record_indices` nếu là node lá
- các con trỏ tới object/activity/prop liên quan

Ý nghĩa:

- cây chỉ mục theo thời gian
- truy vấn khoảng frame sẽ đi trên cây

## 6. Ý Nghĩa Của Các Array

Ngoài cây, hệ thống còn có:

- `OBJECTARRAY`
  - chỉ mục theo object
- `ACTIVITYARRAY`
  - chỉ mục theo activity
- `PROPARRAY`
  - chỉ mục theo thuộc tính

Vai trò:

- truy vấn theo object/activity/prop không cần quét toàn bộ `segment_table`
- có thể lấy nhanh các record liên quan qua `record_indices`

## 7. Tạo Cây Và Chỉ Mục

Quy trình xây dựng hệ thống:

1. Đọc `segment table`
2. Tạo `SegmentRecord`
3. Nhóm dữ liệu theo `video_id`
4. Xây `RS-tree` cho từng video
5. Tạo `OBJECTARRAY`
6. Tạo `ACTIVITYARRAY`
7. Tạo `PROPARRAY`

Ví dụ tạo hệ thống từ dữ liệu mẫu:

Phần tạo cây được thực hiện theo hướng bottom-up, tức là xây cây từ dưới lên. Đầu tiên hệ thống sắp xếp các `segment` theo `frame`, sau đó chia thành các nhóm nhỏ để tạo `leaf node`, mỗi `leaf` giữ các `record_indices` của segment gốc. Tiếp theo, nhiều `leaf` được gom lại thành `internal node`, mỗi `internal node` lưu `children` và khoảng `frame` bao phủ toàn bộ các node con. Quá trình này được lặp lại cho đến khi còn một node gốc `ROOT` cho video đó.

```python
from chapter7_core import build_demo_system

system = build_demo_system(max_entries=4)
print(len(system.segment_table))
print(system.video_trees.keys())
```

Hoặc nạp từ file JSON:

```python
from pathlib import Path
from chapter7_core import VideoSegmentSystem

data_path = Path("chapter7_sample_segments.json")
system = VideoSegmentSystem.from_json(data_path, max_entries=4)
```

## 8. Tám Phép Truy Vấn Cơ Bản

Hệ thống hỗ trợ 8 truy vấn chính:

1. `FindVideoWithObject(o)`
2. `FindVideoWithActivity(a)`
3. `FindVideoWithActivityandProp(a,p,z)`
4. `FindVideoWithObjectandProp(o,p,z)`
5. `FindObjectsInVideo(v,s,e)`
6. `FindActivitiesInVideo(v,s,e)`
7. `FindActivitiesAndPropsinVideo(v,s,e)`
8. `FindObjectsAndPropsinVideo(v,s,e)`

## 9. Các Dạng Truy Vấn Và Ví Dụ Code

### Truy vấn theo object / activity / prop

Các hàm như:

- `FindVideoWithObject`
- `FindVideoWithActivity`
- `FindVideoWithObjectandProp`
- `FindVideoWithActivityandProp`

sẽ dùng:

- `OBJECTARRAY`
- `ACTIVITYARRAY`
- `PROPARRAY`

Ví dụ:

```python
from chapter7_core import build_demo_system

system = build_demo_system()

print(system.FindVideoWithObject("person").values)
print(system.FindVideoWithActivity("running").values)
print(system.FindVideoWithObjectandProp("person", "item", "bag").values)
print(system.FindVideoWithActivityandProp("running", "location", "park").values)
```

### Truy vấn theo khoảng frame

Các hàm như:

- `FindObjectsInVideo`
- `FindActivitiesInVideo`
- `FindActivitiesAndPropsinVideo`
- `FindObjectsAndPropsinVideo`

sẽ đi trên `RS-tree` của video tương ứng.

Ví dụ:

```python
from chapter7_core import build_demo_system

system = build_demo_system()

print(system.FindObjectsInVideo("demo_video_01", 10, 20).values)
print(system.FindActivitiesInVideo("demo_video_01", 20, 80).values)
print(system.FindActivitiesAndPropsinVideo("demo_video_01", 20, 80).values)
print(system.FindObjectsAndPropsinVideo("demo_video_01", 20, 80).values)
```

## 10. Chèn Dữ Liệu Động

Chapter 7 hiện đã hỗ trợ `insert động`.

Khi thêm một segment mới:

1. thêm vào `segment_table`
2. cập nhật `OBJECTARRAY`
3. cập nhật `ACTIVITYARRAY`
4. cập nhật `PROPARRAY`
5. chèn record vào `RS-tree`
6. nếu node tràn thì `split`

Ví dụ chèn thêm một object mới vào video:

```python
from chapter7_core import build_demo_system

system = build_demo_system(max_entries=4)

system.add_segment({
    "segment_id": 33,
    "video_id": "demo_video_01",
    "start_frame": 1,
    "end_frame": 20,
    "object_name": "bird",
    "activity_name": "flying",
    "object_props": {"location": "park"},
    "activity_props": {"location": "park"},
})

print(system.FindVideoWithObject("bird").values)
print(system.FindObjectsInVideo("demo_video_01", 1, 20).values)
```

Ý nghĩa:

- hệ thống không cần rebuild toàn bộ cây sau mỗi insert
- phù hợp hơn với ý tưởng index động

## 11. Kết Hợp Truy Vấn

Ngoài 8 phép cơ bản, hệ thống còn hỗ trợ kết hợp truy vấn video bằng:

- `AND`
- `OR`
- `NOT`

Ví dụ kết hợp 2 truy vấn:

```python
from chapter7_core import build_demo_system

system = build_demo_system()

r1 = system.run_video_query("FindVideoWithObject", o="person", a="", p="", z="")
r2 = system.run_video_query("FindVideoWithObject", o="car", a="", p="", z="")

print(system.combine_video_results(r1, "AND", r2).values)
print(system.combine_video_results(r1, "NOT", r2).values)
```

Ví dụ kết hợp nhiều điều kiện:

```python
from chapter7_core import build_demo_system

system = build_demo_system()

conditions = [
    {"query": "FindVideoWithObject", "params": {"o": "person", "a": "", "p": "", "z": ""}},
    {"operator": "AND", "query": "FindVideoWithActivity", "params": {"o": "", "a": "running", "p": "", "z": ""}},
    {"operator": "NOT", "query": "FindVideoWithObject", "params": {"o": "car", "a": "", "p": "", "z": ""}},
]

print(system.evaluate_video_conditions(conditions).values)
```

Hệ thống đánh giá theo thứ tự từ trái sang phải.

## 12. Giao Diện Demo

Phần GUI nằm trong `7B.py`.

GUI hỗ trợ:

- nạp dữ liệu mẫu
- chạy 8 phép truy vấn cơ bản
- kết hợp nhiều điều kiện truy vấn
- thêm hoặc bớt số vế truy vấn
- cuộn giao diện khi có nhiều điều kiện

Chạy GUI:

```powershell
python 7B.py
```

## 13. Các Tệp Chính

- `chapter7_core.py`
  - phần lõi của hệ thống
- `7A.py`
  - wrapper export lại các thành phần chính
- `7B.py`
  - giao diện demo
- `chapter7_sample_segments.json`
  - dữ liệu mẫu

## 14. Ưu Điểm

- có chỉ mục theo frame bằng `RS-tree`
- có chỉ mục theo `object`, `activity`, `prop`
- hỗ trợ truy vấn video linh hoạt
- có GUI trực quan
- đã hỗ trợ insert động

## 15. Hạn Chế

- dữ liệu demo vẫn còn nhỏ
- `RS-tree` hiện ở mức demo học thuật
- chiến lược split chưa tối ưu overlap như các hệ chỉ mục lớn

## 16. Cách Chạy

Chạy GUI:

```powershell
python 7B.py
```

Chạy phần lõi:

```powershell
python chapter7_core.py
```

## 17. Kết Luận

Chapter 7 xây dựng một hệ truy vấn video dựa trên:

- `RS-tree`
- `OBJECTARRAY`
- `ACTIVITYARRAY`
- `PROPARRAY`

Hệ thống hiện hỗ trợ:

- 8 phép truy vấn cơ bản
- truy vấn kết hợp
- insert động
- GUI demo trực quan
