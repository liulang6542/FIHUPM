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
            'name': stage_name,
            'start_time': time.time(),
            'start_memory': self.get_memory_usage()
        }

    def end_stage(self, stage_info):
        end_time = time.time()
        end_memory = self.get_memory_usage()

        stage_info['end_time'] = end_time
        stage_info['end_memory'] = end_memory
        stage_info['duration'] = end_time - stage_info['start_time']
        stage_info['memory_delta'] = end_memory - stage_info['start_memory']
        stage_info['peak_memory'] = end_memory

        self.stage_stats.append(stage_info)
        return stage_info

    def get_memory_usage(self):
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except:
            return 0.0

    def print_stage_performance(self, stage_info):
        print(f"  运行时间：{stage_info['duration']:.4f} 秒")
        print(f"  内存使用：{stage_info['end_memory']:.2f} MB")
        print(f"  内存变化：{stage_info['memory_delta']:+.2f} MB")

    def print_final_summary(self):
        if not self.stage_stats:
            return

        header("性能统计汇总")
        print("阶段名称".ljust(25) + " | " + "运行时间(秒)".rjust(12) + " | " + "内存使用(MB)".rjust(
            12) + " | " + "内存变化(MB)".rjust(12))
        print("-" * 70)

        total_time = 0
        max_memory = 0

        for stage in self.stage_stats:
            total_time += stage['duration']
            max_memory = max(max_memory, stage['end_memory'])

            memory_change_str = f"{stage['memory_delta']:+.2f}"
            print(
                f"{stage['name'][:24].ljust(25)} | {stage['duration']:>12.4f} | {stage['end_memory']:>12.2f} | {memory_change_str:>12}")

        print("-" * 70)
        print(f"{'总计'.ljust(25)} | {total_time:>12.4f} | {max_memory:>12.2f} | {'峰值内存':>12}")

        print(f"\n详细统计：")
        print(f"  总运行时间：{total_time:.4f} 秒")
        print(f"  峰值内存：{max_memory:.2f} MB")
        print(f"  平均每阶段时间：{total_time / len(self.stage_stats):.4f} 秒")
        print(f"  处理了 {len(self.stage_stats)} 个阶段")


class MemoryOptimizedJoinTrie:
    def __init__(self):
        self.nodes = {}

    def add_singleton_ul(self, ul):
        key = frozenset(ul["itemset"])
        if key in self.nodes:
            twu, total_util = self.nodes[key]
            self.nodes[key] = (twu + ul["twu"], total_util + ul["total_util"])
        else:
            self.nodes[key] = (ul["twu"], ul["total_util"])

    def add_candidate_from_join(self, cand):
        key = frozenset(cand["itemset"])
        if key in self.nodes:
            twu, total_util = self.nodes[key]
            self.nodes[key] = (twu + cand["twu"], total_util + cand["total_util"])
        else:
            self.nodes[key] = (cand["twu"], cand["total_util"])

    def update_with_transaction(self, trans, TU, unit_utility):
        u_item = {}
        for i, qty in trans:
            u = qty * unit_utility[i]
            if u != 0:
                u_item[i] = u

        if not u_item:
            return

        items = sorted(u_item.keys())

        for key in list(self.nodes.keys()):
            itemset = set(key)
            if itemset.issubset(set(items)):
                util = sum(u_item[item] for item in itemset)
                twu, total_util = self.nodes[key]
                self.nodes[key] = (twu + TU, total_util + util)

    def get_node_stats(self, itemset):
        key = frozenset(itemset)
        if key in self.nodes:
            twu, total_util = self.nodes[key]
            return {'total_util': total_util, 'twu': twu}
        return None

    def update_stage_large_from_trie(self, stage_large, total_TU_sum):
        updated_large = []
        for ul in stage_large:
            node_stats = self.get_node_stats(ul["itemset"])
            if node_stats:
                ul["total_util"] = node_stats["total_util"]
                ul["twu"] = node_stats["twu"]
                ul["TWUr"] = (node_stats["twu"] / total_TU_sum) if total_TU_sum > 0 else 0.0
            updated_large.append(ul)
        return updated_large

    def clear_memory(self):
        self.nodes.clear()


def parse_transaction(s):
    return [(int(item), int(qty)) for item, qty in (p.split(',') for p in s.strip().split())]


def compute_TU(trans, unit_utility):
    return sum(unit_utility[i] * qty for i, qty in trans)


def fmt_set(s):
    return "{" + ", ".join(map(str, sorted(list(s)))) + "}"


def header(title):
    print("\n" + "=" * 12 + f" {title} " + "=" * 12)


def optimized_build_1_itemsets_with_ul(transactions, start_tid, unit_utility):
    TU_list = [compute_TU(t, unit_utility) for t in transactions]
    TU_sum = sum(TU_list)
    item_info = {}

    for idx, t in enumerate(transactions):
        tid = start_tid + idx
        TU_val = TU_list[idx]
        for item, qty in t:
            util = qty * unit_utility[item]
            if item not in item_info:
                item_info[item] = {
                    "itemset": {item},
                    "twu": 0,
                    "total_util": 0,
                    "tids": {}
                }
            item_info[item]["twu"] += TU_val
            item_info[item]["total_util"] += util
            item_info[item]["tids"][tid] = item_info[item]["tids"].get(tid, 0) + util

    result_list = []
    for item_data in item_info.values():
        item_data["TWUr"] = item_data["twu"] / TU_sum if TU_sum > 0 else 0.0
        result_list.append(item_data)

    item_info.clear()
    TU_list.clear()

    return result_list, TU_sum


def memory_efficient_update_baseline_append_only(baseline_order, baseline_items_ids, inc_1items, TU_sum_all):
    for itm in inc_1items:
        item_id = list(itm["itemset"])[0]
        if item_id in baseline_items_ids:
            for base in baseline_order:
                if list(base["itemset"])[0] == item_id:
                    base["twu"] += itm["twu"]
                    base["total_util"] += itm["total_util"]
                    if "tids" not in base:
                        base["tids"] = {}
                    for tid, u in itm["tids"].items():
                        base["tids"][tid] = base["tids"].get(tid, 0) + u
                    break
        else:
            baseline_order.append(itm)
            baseline_items_ids.append(item_id)

        itm["tids"].clear()

    for base in baseline_order:
        base["TWUr"] = base["twu"] / TU_sum_all if TU_sum_all > 0 else 0.0

    return baseline_order


def join_k_from_kminus1(ulA, ulB, ulPrefix, all_TU_sum, transaction_TU_list):
    tA, tB = ulA["tids"], ulB["tids"]
    if len(tA) > len(tB):
        ulA, ulB = ulB, ulA
        tA, tB = tB, tA
    new_tids, twu, total_util = {}, 0, 0
    if ulPrefix is None:
        for tid, uA in tA.items():
            if tid in tB:
                u = uA + tB[tid]
                new_tids[tid] = u
                twu += transaction_TU_list[tid - 1]
                total_util += u
    else:
        tP = ulPrefix["tids"]
        for tid, uA in tA.items():
            if tid in tB:
                u = uA + tB[tid] - tP.get(tid, 0)
                new_tids[tid] = u
                twu += transaction_TU_list[tid - 1]
                total_util += u
    if not new_tids:
        return None
    return {
        "itemset": ulA["itemset"] | ulB["itemset"],
        "twu": twu,
        "total_util": total_util,
        "tids": new_tids,
        "TWUr": (twu / all_TU_sum) if all_TU_sum > 0 else 0.0,
    }


def optimized_mine_with_utility_thresholds(baseline_order, total_TU_sum, transaction_TU_list, Su, Sl, phase_name="",
                                           trie=None):
    cur_sum = total_TU_sum
    util_su = Su * cur_sum
    ul_map = {frozenset(ul["itemset"]): ul for ul in baseline_order}
    results_large = []
    L = []
    temp_ul_list = []

    for ul in baseline_order:
        if trie is not None and (ul["TWUr"] >= Sl or ul["total_util"] >= util_su):
            trie.add_singleton_ul(ul)
        if ul["total_util"] >= util_su:
            results_large.append(ul)
        if ul["TWUr"] >= Su:
            L.append(ul)

    k = 1
    while L:
        print(f"[k={k}] joinable 数量={len(L)}")
        if k == 1:
            groups = {(): L}
        else:
            groups = defaultdict(list)
            for ul in L:
                items = sorted(list(ul["itemset"]))
                prefix = tuple(items[:-1])
                groups[prefix].append(ul)

        next_L = []
        for prefix_key, siblings in groups.items():
            prefix_ul = None if k == 1 else ul_map.get(frozenset(prefix_key), None)
            sib_sorted = sorted(siblings, key=lambda x: sorted(list(x["itemset"]))[-1])

            for i in range(len(sib_sorted)):
                for j in range(i + 1, len(sib_sorted)):
                    A, B = sib_sorted[i], sib_sorted[j]
                    cand = join_k_from_kminus1(A, B, prefix_ul, cur_sum, transaction_TU_list)
                    if not cand:
                        continue

                    if trie is not None and (cand["TWUr"] >= Sl or cand["total_util"] >= util_su):
                        trie.add_candidate_from_join(cand)
                    if cand["TWUr"] >= Su:
                        next_L.append(cand)
                        temp_ul_list.append(cand)
                        if cand["total_util"] >= util_su:
                            results_large.append(cand)

                    key = frozenset(cand["itemset"])
                    if key not in ul_map:
                        ul_map[key] = cand

        L = next_L
        k += 1

    ul_map.clear()
    groups.clear()

    for temp_ul in temp_ul_list:
        if "tids" in temp_ul:
            del temp_ul["tids"]
    return results_large


def print_inherited_large(prev_large, total_TU_sum, Su, phase_name=""):
    util_su = Su * total_TU_sum
    kept = []
    for ul in prev_large:
        if ul["total_util"] >= util_su:
            kept.append(ul)
    return kept


def read_db_and_profit(db_path, profit_path):
    with open(db_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    unit_utility = {}
    with open(profit_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                a, b = line.strip().split(",")
                unit_utility[int(a)] = int(b)

    return lines, unit_utility


def split_dataset_by_insertion_rate(all_transactions, insertion_rate, num_increments):
    total_count = len(all_transactions)
    original_count = int(total_count * (1 - insertion_rate))
    increment_count = total_count - original_count

    print(f"数据集分割信息：")
    print(f"  总事务数：{total_count}")
    print(f"  插入率：{insertion_rate} ({insertion_rate * 100}%)")
    print(f"  原始数据集：{original_count} 个事务 ({(1 - insertion_rate) * 100:.1f}%)")
    print(f"  增量数据：{increment_count} 个事务 ({insertion_rate * 100}%)")

    original_transactions = all_transactions[:original_count]
    remaining_transactions = all_transactions[original_count:]

    increment_batches = []
    batch_size = math.ceil(increment_count / num_increments)

    for i in range(num_increments):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, increment_count)
        if start_idx < increment_count:
            batch = remaining_transactions[start_idx:end_idx]
            if batch:
                increment_batches.append(batch)

    return original_transactions, increment_batches


def prepare_transactions(str_list):
    return [parse_transaction(s) for s in str_list]


def update_transaction_TU_list(transaction_TU_list, transactions, start_tid, unit_utility):
    for idx, trans in enumerate(transactions, start_tid):
        while len(transaction_TU_list) < idx:
            transaction_TU_list.append(0)
        transaction_TU_list[idx - 1] = compute_TU(trans, unit_utility)


def update_trie_with_batch(trie, transactions, start_tid, unit_utility, transaction_TU_list):
    for idx, trans in enumerate(transactions, start_tid):
        TU = transaction_TU_list[idx - 1]
        trie.update_with_transaction(trans, TU, unit_utility)


def cleanup_stage_data():
    gc.collect()


if __name__ == "__main__":
    monitor = PerformanceMonitor()

    program_start = monitor.start_stage("程序总体运行")

    stage1_start = monitor.start_stage("阶段1（原始挖掘）")

    all_transaction_lines, unit_utility = read_db_and_profit(DB_PATH, PROFIT_PATH)

    original_str, increment_batches_str = split_dataset_by_insertion_rate(
        all_transaction_lines, INSERTION_RATE, NUM_INCREMENTS
    )

    original_transactions = prepare_transactions(original_str)
    increment_batches = [prepare_transactions(batch) for batch in increment_batches_str]

    transaction_TU_list = []
    current_tid = 1

    update_transaction_TU_list(transaction_TU_list, original_transactions, current_tid, unit_utility)
    original_1items, original_TU_sum = optimized_build_1_itemsets_with_ul(
        original_transactions, start_tid=current_tid, unit_utility=unit_utility
    )

    baseline_order = sorted(original_1items, key=lambda x: (x["twu"], min(x["itemset"])))
    baseline_items_ids = [list(itm["itemset"])[0] for itm in baseline_order]
    total_TU_sum = original_TU_sum
    current_tid += len(original_transactions)

    trie = MemoryOptimizedJoinTrie()

    stage_large = optimized_mine_with_utility_thresholds(
        baseline_order, total_TU_sum, transaction_TU_list, Su, Sl,
        phase_name="阶段1", trie=trie
    )

    monitor.end_stage(stage1_start)
    monitor.print_stage_performance(stage1_start)
    cleanup_stage_data()

    TU_base = original_TU_sum
    buf_cum = 0

    for batch_idx, inc_transactions in enumerate(increment_batches, 1):
        if not inc_transactions:
            continue

        stage_name = f"阶段{batch_idx + 1}（增量批次{batch_idx}）"
        batch_start = monitor.start_stage(stage_name)

        update_transaction_TU_list(transaction_TU_list, inc_transactions, current_tid, unit_utility)

        inc_1items, inc_TU_sum = optimized_build_1_itemsets_with_ul(
            inc_transactions, start_tid=current_tid, unit_utility=unit_utility
        )

        buf_cum += inc_TU_sum
        total_TU_sum += inc_TU_sum
        current_tid += len(inc_transactions)

        baseline_order = memory_efficient_update_baseline_append_only(
            baseline_order, baseline_items_ids, inc_1items, total_TU_sum
        )
        baseline_order.sort(key=lambda x: (x["twu"], min(x["itemset"])))

        lhs = (1 - Su) * buf_cum
        rhs = (Su - Sl) * TU_base
        print(
            f"\n[{stage_name}  重扫描? {lhs >= rhs}")

        if lhs >= rhs:
            header(f"{stage_name}：触发重扫描 → 完整拼接挖掘")
            trie = MemoryOptimizedJoinTrie()
            stage_large = optimized_mine_with_utility_thresholds(
                baseline_order, total_TU_sum, transaction_TU_list, Su, Sl,
                phase_name=stage_name, trie=trie
            )

            TU_base = total_TU_sum
            buf_cum = 0
        else:
            header(f"{stage_name}：继承模式 → 增量更新")

            update_trie_with_batch(trie, inc_transactions, current_tid - len(inc_transactions), unit_utility,
                                   transaction_TU_list)

            stage_large = trie.update_stage_large_from_trie(stage_large, total_TU_sum)

            util_su = Su * total_TU_sum
            known = {frozenset(ul["itemset"]) for ul in stage_large}
            for key, (twu, total_util) in trie.nodes.items():
                if total_util >= util_su and key not in known:
                    stage_large.append({
                        "itemset": set(key),
                        "twu": twu,
                        "total_util": total_util,
                        "TWUr": (twu / total_TU_sum) if total_TU_sum > 0 else 0.0
                    })

            stage_large = [ul for ul in stage_large if ul["total_util"] >= util_su]
        monitor.end_stage(batch_start)
        monitor.print_stage_performance(batch_start)
        cleanup_stage_data()
    if trie:
        trie.clear_memory()
    monitor.end_stage(program_start)

    header("最终挖掘结果汇总")
    print(f"原始数据集大小：{len(original_transactions)} 个事务")
    print(f"处理了 {len(increment_batches)} 个增量批次")
    print(f"总事务数：{current_tid - 1}")

    # —— 仅输出项集（去重并按项集长度、字典序排序）——
    if stage_large:
        # 用集合去重，再转为有序元组方便排序
        final_itemsets = sorted(
            {tuple(sorted(ul["itemset"])) for ul in stage_large},
            key=lambda it: (len(it), it)
        )
        print("最终高效用项集（仅项集）：")
        for items in final_itemsets:
            # 复用你已有的 fmt_set 辅助函数来美化输出
            print(fmt_set(set(items)))
    else:
        print("未发现任何高效用项集。")

    monitor.print_final_summary()

