import { invalidationsFor } from "../../../../../app/product_v2/domain/invalidation.js";

// 独立负例：图身份必须是字符串，不能把列表索引当成持久化身份。
invalidationsFor("shot_spec_changed", { shotId: 42 });
