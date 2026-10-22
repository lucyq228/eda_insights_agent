---
name: prepare-data
description: Create a clean base table while preserving identifiers, metric components and original categories.
---
Run prepare_data.py after data quality. Deduplicate exact rows, remove missing target rows,
encode the target and parse dates. Preserve all other source columns. Predictor exclusions
apply only to model inputs. Aggregate views are derived at analysis time, with lineage.
No automatic rare-category pooling. Original categories remain available for full analysis;
chart display limits must not change the underlying association test.
