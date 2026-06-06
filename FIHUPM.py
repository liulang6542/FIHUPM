#输入数据集中不存在效用效用值为0或负数的情况，并且事务内无重复 item
from collections import defaultdict
import math
import time
import psutil
import os
import gc

Su, Sl = 0.16, 0.1
DB_PATH = r"C:\Users\lx\pythonProject5\对比算法2025\mushroom.txt"
PROFIT_PATH = r"C:\Users\lx\pythonProject5\对比算法2025\mushroomfprofit.txt"
INSERTION_RATE = 0.3
NUM_INCREMENTS = 9


class PerformanceMonitor:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.stage_stats = []

    def start_stage(self, stage_name):
        return {
            "name": stage_name,
            "start_time": time.time(),
            "start_memory": self.get_memory_usage(),
        }

    def end_stage(self, stage_info):
        end_time = time.time()
        end_memory = self.get_memory_usage()
        stage_info["end_time"] = end_time
        stage_info["end_memory"] = end_memory
        stage_info["duration"] = end_time - stage_info["start_time"]
        stage_info["memory_delta"] = end_memory - stage_info["start_memory"]
        stage_info["peak_memory"] = end_memory
        self.stage_stats.append(stage_info)
        return stage_info

    def get_memory_usage(self):
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    def print_stage_performance(self, stage_info):
        print(f"   运行时间：{stage_info['duration']:.4f} 秒")
        print(f"   内存使用：{stage_info['end_memory']:.2f} MB")
        print(f"   内存变化：{stage_info['memory_delta']:+.2f} MB")

    def print_final_summary(self):
        if not self.stage_stats:
            return
        header("性能统计汇总")
        print(
            "阶段名称".ljust(25)
            + " | "
            + "运行时间(秒)".rjust(12)
            + " | "
            + "内存使用(MB)".rjust(12)
            + " | "
            + "内存变化(MB)".rjust(12)
        )
        print("-" * 70)
        total_time = 0
        max_memory = 0
        for stage in self.stage_stats:
            total_time += stage["duration"]
            max_memory = max(max_memory, stage["end_memory"])
            mem_str = f"{stage['memory_delta']:+.2f}"
            print(
                f"{stage['name'][:24].ljust(25)} | "
                f"{stage['duration']:>12.4f} | "
                f"{stage['end_memory']:>12.2f} | "
                f"{mem_str:>12}"
            )
        print("-" * 70)
        print(
            f"{'总计'.ljust(25)} | {total_time:>12.4f} | "
            f"{max_memory:>12.2f} | {'峰值内存':>12}"
        )
        print("\n详细统计：")
        print(f"   峰值内存：{max_memory:.2f} MB")
        print(f"   平均每阶段时间：{total_time / len(self.stage_stats):.4f} 秒")
        print(f"   处理了 {len(self.stage_stats)} 个阶段")


def header(title):
    print("\n" + "=" * 12 + f" {title} " + "=" * 12)


def parse_transaction(s):
    return [(int(item), int(qty)) for item, qty in (p.split(",") for p in s.strip().split())]


def compute_TU(trans, unit_utility):
    return sum(unit_utility.get(i, 0) * qty for i, qty in trans)


def read_db_and_profit(db_path, profit_path):
    with open(db_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    unit_utility = {}
    with open(profit_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                a, b = line.strip().split(",")
                unit_utility[int(a)] = float(b)
    return lines, unit_utility


def prepare_transactions(str_list):
    return [parse_transaction(s) for s in str_list]


def split_dataset_by_insertion_rate(all_transactions, insertion_rate, num_increments):
    total_count = len(all_transactions)
    original_count = int(total_count * (1 - insertion_rate))
    increment_count = total_count - original_count
    print("数据集分割信息：")
    print(f"  总事务数：{total_count}")
    print(f"  插入率：{insertion_rate} ({insertion_rate * 100:.2f}%)")
    print(f"  原始数据集：{original_count} 个事务 ({(1 - insertion_rate) * 100:.2f}%)")
    print(f"  增量数据：{increment_count} 个事务 ({insertion_rate * 100:.2f}%)")
    original_transactions = all_transactions[:original_count]
    remaining_transactions = all_transactions[original_count:]
    increment_batches = []
    batch_size = math.ceil(increment_count / num_increments) if num_increments > 0 else increment_count
    for i in range(num_increments):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, increment_count)
        if start_idx < increment_count:
            batch = remaining_transactions[start_idx:end_idx]
            if batch:
                increment_batches.append(batch)
    return original_transactions, increment_batches


class GlobalIHI:
    def __init__(self):
        self.tids = defaultdict(dict)
        self.twu = defaultdict(float)
        self.total_util = defaultdict(float)
        self.tu_list = []
        self.prev_TWUr = {}
        self.prev_total_TU = 0.0

    def append_batch(self, transactions, start_tid, unit_utility):
        batch_TU = 0.0
        for idx, t in enumerate(transactions, start_tid):
            TU_t = float(compute_TU(t, unit_utility))
            while len(self.tu_list) < idx:
                self.tu_list.append(0.0)
            self.tu_list[idx - 1] = TU_t
            batch_TU += TU_t
            if TU_t == 0:
                continue
            for i, qty in t:
                u = qty * unit_utility.get(i, 0.0)
                if u == 0:
                    continue
                self.tids[i][idx] = self.tids[i].get(idx, 0.0) + u
                self.total_util[i] += u
                self.twu[i] += TU_t
        return batch_TU

    def current_TWUr(self, i, total_TU):
        if total_TU <= 0:
            return 0.0
        return self.twu.get(i, 0.0) / total_TU

    def snapshot_TWUr(self, total_TU):
        return {i: self.current_TWUr(i, total_TU) for i in self.tids.keys()}


def join_two_lists(A_tids, B_tids, prefix_tids):
    if len(A_tids) > len(B_tids):
        A_tids, B_tids = B_tids, A_tids
    out = {}
    total = 0.0
    for tid, uA in A_tids.items():
        uB = B_tids.get(tid)
        if uB is None:
            continue
        u = uA + uB
        if prefix_tids is not None:
            u -= prefix_tids.get(tid, 0.0)
        if u == 0:
            continue
        out[tid] = u
        total += u
    return out, total


def twu_of_tids(tids_dict, tu_list):
    s = 0.0
    for tid in tids_dict.keys():
        if tid - 1 < len(tu_list):
            s += tu_list[tid - 1]
    return s


def build_suffix_after(transactions_iter, start_tid, unit_utility, item_order_map):
    suffix_after = {}
    for idx, t in enumerate(transactions_iter, start_tid):
        vec = []
        for i, qty in t:
            u = unit_utility.get(i, 0.0) * qty
            if u != 0.0:
                vec.append((i, u))
        if not vec:
            suffix_after[idx] = {}
            continue
        vec.sort(key=lambda x: item_order_map.get(x[0], 10**9))
        s = 0.0
        m = {}
        for i, u in reversed(vec):
            m[i] = s
            s += u
        suffix_after[idx] = m
    return suffix_after


def _build_suffix_cache(scope_items, global_ihi, item_order_map):
    tid_to_items_u = defaultdict(dict)
    for i in scope_items:
        for tid, u in global_ihi.tids[i].items():
            tid_to_items_u[tid][i] = u

    cache = {}

    def get_suffix_after(tid):
        if tid in cache:
            return cache[tid]
        items_u = tid_to_items_u.get(tid, {})
        ordered = sorted(items_u.items(), key=lambda x: item_order_map.get(x[0], 10**9))
        s = 0.0
        m = {}
        for i, u in reversed(ordered):
            m[i] = s
            s += u
        cache[tid] = m
        return m

    return get_suffix_after


class PatternStore:
    def __init__(self):
        self.patterns = {}

    def add(self, itemset, twu, total_util):
        key = frozenset(itemset)
        if key not in self.patterns:
            self.patterns[key] = {
                "twu": twu,
                "total_util": total_util,
                "TWUr": 0.0,
                "category": "small",
            }
        else:
            p = self.patterns[key]
            p["twu"] = twu
            p["total_util"] = total_util

    def get(self, key):
        return self.patterns.get(frozenset(key))

    def __contains__(self, key):
        return frozenset(key) in self.patterns

    def __len__(self):
        return len(self.patterns)

    def all_patterns(self):
        return self.patterns.items()

    def reclassify(self, total_TU, Su, Sl):
        util_su = Su * total_TU
        util_sl = Sl * total_TU
        for key, p in self.patterns.items():
            p["TWUr"] = p["twu"] / total_TU if total_TU > 0 else 0.0
            if p["total_util"] >= util_su:
                p["category"] = "large"
            elif p["total_util"] >= util_sl:
                p["category"] = "pre_large"
            else:
                p["category"] = "small"


def incremental_update_existing_patterns(inc_transactions, start_tid, unit_utility, patterns, global_ihi):
    inv = defaultdict(list)
    for key in patterns.patterns.keys():
        for it in key:
            inv[it].append(key)

    for idx, t in enumerate(inc_transactions, start_tid):
        u_map = {}
        items = set()
        for i, qty in t:
            u = unit_utility.get(i, 0.0) * qty
            if u != 0:
                u_map[i] = u_map.get(i, 0.0) + u
                items.add(i)
        if not items:
            continue
        TU_t = global_ihi.tu_list[idx - 1] if idx - 1 < len(global_ihi.tu_list) else 0.0
        visited = set()
        for i in items:
            for key in inv.get(i, []):
                if key in visited:
                    continue
                visited.add(key)
                if key.issubset(items):
                    inc_u = sum(u_map[x] for x in key)
                    if inc_u != 0:
                        p = patterns.patterns[key]
                        p["total_util"] += inc_u
                        p["twu"] += TU_t


def make_rescan_order(global_ihi, RescanItems, StableItems, base_item_order_map):
    all_items = set(global_ihi.tids.keys())
    new_rescan_items = {i for i in RescanItems if i not in base_item_order_map}
    old_rescan_items = RescanItems - new_rescan_items
    other_items = all_items - RescanItems - StableItems
    new_rescan_part = sorted(new_rescan_items)
    old_rescan_part = sorted(old_rescan_items, key=lambda i: (base_item_order_map.get(i, 10**9), i))
    stable_part = sorted(StableItems, key=lambda i: (base_item_order_map.get(i, 10**9), i))
    other_part = sorted(
        other_items,
        key=lambda i: (
            0 if i not in base_item_order_map else 1,
            base_item_order_map.get(i, 10**9),
            i,
        ),
    )
    item_order = new_rescan_part + old_rescan_part + stable_part + other_part
    item_order_map = {it: pos for pos, it in enumerate(item_order)}
    return item_order, item_order_map


def _expand_with_trigger(trigger_items, partner_items, item_order, item_order_map, global_ihi, tu_list, get_suffix_after, total_TU, Su, Sl, patterns):
    util_sl = Sl * total_TU

    for i in partner_items:
        if global_ihi.total_util[i] >= util_sl:
            patterns.add({i}, global_ihi.twu[i], global_ihi.total_util[i])

    for r in trigger_items:
        r_tids = dict(global_ihi.tids[r])
        if not r_tids:
            continue
        r_rank = item_order_map[r]
        ext = [j for j in partner_items if item_order_map[j] > r_rank]
        ext.sort(key=lambda x: item_order_map[x])
        _recursive_expand(
            prefix_items=[r],
            prefix_tids=r_tids,
            prefix_total_util=global_ihi.total_util[r],
            ext_items=ext,
            global_ihi=global_ihi,
            tu_list=tu_list,
            get_suffix_after=get_suffix_after,
            item_order_map=item_order_map,
            util_sl=util_sl,
            patterns=patterns,
        )


def _recursive_expand(prefix_items, prefix_tids, prefix_total_util, ext_items, global_ihi, tu_list, get_suffix_after, item_order_map, util_sl, patterns):
    last_anchor = prefix_items[-1]
    ru_prefix = 0.0
    for tid in prefix_tids.keys():
        ru_prefix += get_suffix_after(tid).get(last_anchor, 0.0)
    ub_prefix = prefix_total_util + ru_prefix

    if ub_prefix < util_sl:
        return

    if prefix_total_util >= util_sl:
        twu_prefix = twu_of_tids(prefix_tids, tu_list)
        patterns.add(prefix_items, twu_prefix, prefix_total_util)

    for idx, j in enumerate(ext_items):
        j_tids = global_ihi.tids[j]
        new_tids, new_total = join_two_lists(prefix_tids, j_tids, None)
        if not new_tids:
            continue
        new_prefix = prefix_items + [j]
        new_ext = ext_items[idx + 1:]
        _recursive_expand(
            prefix_items=new_prefix,
            prefix_tids=new_tids,
            prefix_total_util=new_total,
            ext_items=new_ext,
            global_ihi=global_ihi,
            tu_list=tu_list,
            get_suffix_after=get_suffix_after,
            item_order_map=item_order_map,
            util_sl=util_sl,
            patterns=patterns,
        )


def _detect_stable_cooccurrence(delta_transactions, start_tid, stable_items, unit_utility, global_ihi, item_order_map, get_suffix_after, total_TU, Sl, patterns):
    util_sl = Sl * total_TU

    delta_tid_set = set(range(start_tid, start_tid + len(delta_transactions)))

    stable_list = sorted(stable_items, key=lambda i: item_order_map.get(i, 10**9))

    delta_tids_map = {}
    for i in stable_list:
        d = {tid: u for tid, u in global_ihi.tids[i].items() if tid in delta_tid_set}
        if d:
            delta_tids_map[i] = d

    active_stable = [i for i in stable_list if i in delta_tids_map]
    if len(active_stable) < 2:
        return

    def dfs(prefix_items, global_tids, delta_tids_prefix, candidates):
        for idx, j in enumerate(candidates):
            if j not in delta_tids_map:
                continue
            new_delta = {
                tid: u
                for tid, u in delta_tids_map[j].items()
                if tid in delta_tids_prefix
            }
            if not new_delta:
                continue
            new_global, new_total = join_two_lists(global_tids, global_ihi.tids[j], None)
            if not new_global:
                continue
            new_prefix = prefix_items + [j]
            key = frozenset(new_prefix)
            if key not in patterns.patterns and new_total >= util_sl:
                twu_val = twu_of_tids(new_global, global_ihi.tu_list)
                patterns.add(new_prefix, twu_val, new_total)
            ru = sum(get_suffix_after(tid).get(j, 0.0) for tid in new_global)
            ub = new_total + ru
            if ub < util_sl:
                continue
            dfs(new_prefix, new_global, new_delta, candidates[idx + 1:])

    for i_idx, i in enumerate(active_stable):
        i_global = dict(global_ihi.tids[i])
        i_delta = delta_tids_map[i]
        dfs([i], i_global, i_delta, active_stable[i_idx + 1:])


def partial_rescan(global_ihi, patterns, delta_transactions, delta_start_tid, total_TU, unit_utility, Su, Sl, prev_total_TU, base_item_order_map):
    prev_TWUr = global_ihi.prev_TWUr
    PartnerItems = set()
    RescanItems = set()
    for i in global_ihi.tids.keys():
        cur = global_ihi.current_TWUr(i, total_TU)
        if cur >= Sl:
            PartnerItems.add(i)
            prev = prev_TWUr.get(i, 0.0)
            if prev < Sl:
                RescanItems.add(i)
    StableItems = PartnerItems - RescanItems

    print(f"   PartnerItems: {len(PartnerItems)}, RescanItems: {len(RescanItems)}, StableItems: {len(StableItems)}")

    item_order, item_order_map = make_rescan_order(global_ihi, RescanItems, StableItems, base_item_order_map)

    get_suffix_after = _build_suffix_cache(PartnerItems, global_ihi, item_order_map)

    if RescanItems:
        print(f"   Work B: expanding from {len(RescanItems)} RescanItems")
        _expand_with_trigger(RescanItems, PartnerItems, item_order, item_order_map, global_ihi, global_ihi.tu_list, get_suffix_after, total_TU, Su, Sl, patterns)

    print(f"   Work C: checking {len(delta_transactions)} Δ_t transactions for stable-item co-occurrence")
    _detect_stable_cooccurrence(delta_transactions, delta_start_tid, StableItems, unit_utility, global_ihi, item_order_map, get_suffix_after, total_TU, Sl, patterns)

    patterns.reclassify(total_TU, Su, Sl)
    global_ihi.prev_TWUr = global_ihi.snapshot_TWUr(total_TU)
    global_ihi.prev_total_TU = total_TU

    return item_order, item_order_map, RescanItems, PartnerItems, StableItems


def compute_safety_delta_TU(TU_old, Su, Sl):
    if Su >= 1.0:
        return 0.0
    return ((Su - Sl) / (1.0 - Su)) * TU_old


def within_prelarge_safety(buf, TU_old, Su, Sl):
    return buf <= compute_safety_delta_TU(TU_old, Su, Sl)


def initial_mining(original_transactions, unit_utility, Su, Sl):
    global_ihi = GlobalIHI()
    global_ihi.append_batch(original_transactions, start_tid=1, unit_utility=unit_utility)
    total_TU = sum(global_ihi.tu_list)

    item_order = sorted(global_ihi.tids.keys(), key=lambda i: (global_ihi.current_TWUr(i, total_TU), i))
    item_order_map = {it: pos for pos, it in enumerate(item_order)}

    patterns = PatternStore()
    suffix_after = build_suffix_after(original_transactions, start_tid=1, unit_utility=unit_utility, item_order_map=item_order_map)

    def get_suffix_after(tid):
        return suffix_after.get(tid, {})

    partner_items_init = {i for i in global_ihi.tids.keys() if global_ihi.current_TWUr(i, total_TU) >= Sl}

    _expand_with_trigger(
        trigger_items=partner_items_init,
        partner_items=partner_items_init,
        item_order=item_order,
        item_order_map=item_order_map,
        global_ihi=global_ihi,
        tu_list=global_ihi.tu_list,
        get_suffix_after=get_suffix_after,
        total_TU=total_TU,
        Su=Su,
        Sl=Sl,
        patterns=patterns,
    )

    del suffix_after
    gc.collect()

    patterns.reclassify(total_TU, Su, Sl)
    global_ihi.prev_TWUr = global_ihi.snapshot_TWUr(total_TU)
    global_ihi.prev_total_TU = total_TU

    return global_ihi, patterns, item_order, item_order_map, total_TU


def finalize_huis(patterns, total_TU, Su):
    util_su = Su * total_TU
    return [(key, p) for key, p in patterns.all_patterns() if p["total_util"] >= util_su]


def cleanup_stage_data():
    gc.collect()


if __name__ == "__main__":
    monitor = PerformanceMonitor()
    program_start = monitor.start_stage("程序总体运行")

    stage1 = monitor.start_stage("阶段1（原始挖掘）")
    all_transaction_lines, unit_utility = read_db_and_profit(DB_PATH, PROFIT_PATH)
    all_transactions = prepare_transactions(all_transaction_lines)
    original_transactions, increment_batches = split_dataset_by_insertion_rate(all_transactions, INSERTION_RATE, NUM_INCREMENTS)

    global_ihi, patterns, item_order, item_order_map, total_TU = initial_mining(original_transactions, unit_utility, Su, Sl)
    base_item_order_map = dict(item_order_map)

    huis = finalize_huis(patterns, total_TU, Su)
    print(f"原始挖掘完成。模式总数：{len(patterns)}，large 数量：{len(huis)}")

    monitor.end_stage(stage1)
    monitor.print_stage_performance(stage1)
    cleanup_stage_data()

    current_tid = 1 + len(original_transactions)
    TU_base = total_TU
    last_rescan_tid = current_tid
    buf_cum = 0.0

    for batch_idx, inc_transactions in enumerate(increment_batches, 1):
        if not inc_transactions:
            continue
        stage_name = f"阶段{batch_idx + 1}（增量批次{batch_idx}）"
        batch_stage = monitor.start_stage(stage_name)

        batch_TU = global_ihi.append_batch(inc_transactions, start_tid=current_tid, unit_utility=unit_utility)
        total_TU += batch_TU
        buf_cum += batch_TU

        incremental_update_existing_patterns(inc_transactions, current_tid, unit_utility, patterns, global_ihi)

        need_rescan = not within_prelarge_safety(buf_cum, TU_base, Su, Sl)

        if need_rescan:
            header(f"{stage_name}：触发部分重扫描")
            delta_start_tid = last_rescan_tid
            delta_end_tid = current_tid + len(inc_transactions) - 1
            delta_transactions = all_transactions[delta_start_tid - 1:delta_end_tid]
            item_order, item_order_map, RescanItems, PartnerItems, StableItems = partial_rescan(
                global_ihi=global_ihi,
                patterns=patterns,
                delta_transactions=delta_transactions,
                delta_start_tid=delta_start_tid,
                total_TU=total_TU,
                unit_utility=unit_utility,
                Su=Su,
                Sl=Sl,
                prev_total_TU=TU_base,
                base_item_order_map=base_item_order_map,
            )
            TU_base = total_TU
            buf_cum = 0.0
            last_rescan_tid = delta_end_tid + 1
        else:
            header(f"{stage_name}：仅更新效用（safety 区域内）")
            current_stable = {i for i in global_ihi.tids if global_ihi.current_TWUr(i, total_TU) >= Sl}
            if len(current_stable) >= 2:
                get_suffix_after_safe = _build_suffix_cache(current_stable, global_ihi, item_order_map)
                _detect_stable_cooccurrence(
                    inc_transactions, current_tid, current_stable, unit_utility,
                    global_ihi, item_order_map, get_suffix_after_safe, total_TU, Sl, patterns,
                )
            patterns.reclassify(total_TU, Su, Sl)

        current_tid += len(inc_transactions)
        huis = finalize_huis(patterns, total_TU, Su)
        print(f"当前高效用项集数量：{len(huis)}")
        monitor.end_stage(batch_stage)
        monitor.print_stage_performance(batch_stage)
        cleanup_stage_data()

    header("最终挖掘结果汇总")
    print(f"原始数据集大小：{len(original_transactions)} 个事务")
    print(f"处理了 {len(increment_batches)} 个增量批次")
    print(f"总事务数：{current_tid - 1}")

    patterns.reclassify(total_TU, Su, Sl)
    final_large = finalize_huis(patterns, total_TU, Su)
    print(f"最终 large 模式数量：{len(final_large)}")

    print("最终高效用项集（large，仅项集）：")
    for key, p in sorted(final_large, key=lambda x: (len(x[0]), tuple(sorted(x[0])))):
        print("{" + ", ".join(map(str, sorted(key))) + "}")

    monitor.end_stage(program_start)
    monitor.print_final_summary()
