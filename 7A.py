from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


module_path = Path(__file__).with_name("chapter7_core.py")
spec = importlib.util.spec_from_file_location("chapter7_core", module_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Không thể nạp module từ {module_path}")

module = importlib.util.module_from_spec(spec)
sys.modules["chapter7_core"] = module
spec.loader.exec_module(module)

AccessTraceEntry = module.AccessTraceEntry
ActivityArrayEntry = module.ActivityArrayEntry
FrameSegmentNode = module.FrameSegmentNode
ObjectArrayEntry = module.ObjectArrayEntry
PropArrayEntry = module.PropArrayEntry
QueryResult = module.QueryResult
RSNode = module.RSNode
SegmentRecord = module.SegmentRecord
VideoFrameSegmentTree = module.VideoFrameSegmentTree
VideoRSTree = module.VideoRSTree
VideoSegmentSystem = module.VideoSegmentSystem
build_demo_segment_table = module.build_demo_segment_table
build_demo_system = module.build_demo_system
main = module.main
print_query_result = module.print_query_result


if __name__ == "__main__":
    main()
