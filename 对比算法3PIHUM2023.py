import time
from collections import defaultdict

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _mem_mb():
    if _HAS_PSUTIL:
        return psutil.Process().memory_info().rss / 1024 / 1024
    return 0.0


class ULEntry:
    __slots__ = ("tid", "u", "ru")

    def __init__(self, tid, u, ru=0.0):
        self.tid = tid
        self.u = u
        self.ru = ru


class PIHUPM:
    def __init__(self, su, sl, ir):
        self.su = su
        self.sl = sl
        self.ir = ir
        self.profits = {}
        self.raw_lines = []
        self.all_transactions = []
        self.db = []
        self.base_ids = []
        self.inc_batches = []
        self.original_transactions = []
        self.increment_transactions = []
        self.memory_tids = defaultdict(dict)
        self.memory_twu = defaultdict(float)
        self.memory_total_util = defaultdict(float)
        self.memory_tu_list = []
        self.memory_item_order = []
        self.memory_item_order_map = {}
        self.pattern_tree = {}
        self.results_large = []
        self.results_pre = []
        self.total_utility = 0.0
        self.base_utility = 0.0
        self.buffer_utility = 0.0
        self._orig_base_count = 0
        self._perf_records = []
        self._prog_start = None

    def _transaction_tu(self, t):
        return sum(self.profits.get(i, 0.0) * q for i, q in t.items())

    def _append_memory_index(self, ids):
        for tid0 in ids:
            t = self.db[tid0]
            tid = tid0 + 1
            tu = float(self._transaction_tu(t))

            while len(self.memory_tu_list) < tid:
                self.memory_tu_list.append(0.0)

            self.memory_tu_list[tid - 1] = tu

            if tu == 0:
                continue

            for i, q in t.items():
                u = self.profits.get(i, 0.0) * q
                if u == 0:
                    continue
                self.memory_tids[i][tid] = u
                self.memory_total_util[i] += u
                self.memory_twu[i] += tu

    def _refresh_memory_order(self):
        total_tu = sum(self.memory_tu_list)

        if total_tu <= 0:
            self.memory_item_order = sorted(self.memory_tids.keys())
        else:
            self.memory_item_order = sorted(
                self.memory_tids.keys(),
                key=lambda i: (self.memory_twu.get(i, 0.0) / total_tu, i)
            )

        self.memory_item_order_map = {
            item: pos for pos, item in enumerate(self.memory_item_order)
        }

    def load_data(self, db_file, profit_file):
        profits = {}

        with open(profit_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = [p.strip() for p in line.split(',')]

                if len(parts) == 2:
                    profits[int(parts[0])] = float(parts[1])

        self.profits = profits

        raw_lines = []
        all_transactions = []
        db = []

        with open(db_file) as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                raw_lines.append(line)

                tuple_trans = []
                dict_trans = {}

                for token in line.split():
                    if ',' in token:
                        a, b = token.split(',', 1)
                        item = int(a)
                        qty = int(b)

                        if item in profits:
                            tuple_trans.append((item, qty))
                            dict_trans[item] = qty

                if dict_trans:
                    all_transactions.append(tuple_trans)
                    db.append(dict_trans)

        self.raw_lines = raw_lines
        self.all_transactions = all_transactions
        self.db = db

        n = len(self.db)
        base_size = int(n * (1.0 - self.ir))

        self.base_ids = list(range(base_size))
        rest_ids = list(range(base_size, n))

        self.original_transactions = self.all_transactions[:base_size]
        self.increment_transactions = self.all_transactions[base_size:]

        self.inc_batches = []

        batch_count = 9

        if rest_ids:
            if len(rest_ids) <= batch_count:
                for tid in rest_ids:
                    self.inc_batches.append([tid])
            else:
                bsz = len(rest_ids) // batch_count

                for i in range(batch_count - 1):
                    self.inc_batches.append(rest_ids[i * bsz:(i + 1) * bsz])

                self.inc_batches.append(rest_ids[(batch_count - 1) * bsz:])

        self.memory_tids = defaultdict(dict)
        self.memory_twu = defaultdict(float)
        self.memory_total_util = defaultdict(float)
        self.memory_tu_list = []

        self._append_memory_index(list(range(n)))
        self._refresh_memory_order()

        inc_total = sum(len(b) for b in self.inc_batches)

        print("数据集分割信息：")
        print(f"  总事务数：{n}")
        print(f"  插入率：{self.ir} ({self.ir * 100:.2f}%)")
        print(f"  原始数据集：{base_size} 个事务 ({(1 - self.ir) * 100:.2f}%)")
        print(f"  增量数据：{inc_total} 个事务 ({self.ir * 100:.2f}%)")

    def _iter_trans_by_ids(self, ids):
        for tid in ids:
            yield self.db[tid]

    def _construct(self, trans):
        global_ul = defaultdict(list)
        tu_map = {}
        tid = 0

        for t in trans:
            tid += 1
            items = sorted(i for i in t if i in self.profits)

            if not items:
                continue

            utils = {i: self.profits[i] * t[i] for i in items}
            tu = sum(utils.values())
            tu_map[tid] = tu

            for i in items:
                global_ul[i].append(ULEntry(tid, utils[i], 0.0))

        return global_ul, tu_map

    def _compute_twu(self, global_ul, tu_map):
        return {
            item: sum(tu_map.get(e.tid, 0.0) for e in ul)
            for item, ul in global_ul.items()
        }

    def _filter_and_sort(self, global_ul, twu, min_l):
        keep = {i for i, v in twu.items() if v >= min_l}
        filtered = {i: global_ul[i] for i in keep}
        order = sorted(keep, key=lambda x: (twu[x], x))

        return filtered, order

    def _reconstruct_ru(self, global_ul, order):
        temp = defaultdict(float)

        for item in reversed(order):
            if item not in global_ul:
                continue

            for entry in global_ul[item]:
                entry.ru = temp[entry.tid]
                temp[entry.tid] += entry.u

    def _join2(self, ul1, ul2):
        result = []
        i = j = 0
        n1, n2 = len(ul1), len(ul2)

        while i < n1 and j < n2:
            t1, t2 = ul1[i].tid, ul2[j].tid

            if t1 == t2:
                result.append(
                    ULEntry(
                        t1,
                        ul1[i].u + ul2[j].u,
                        min(ul1[i].ru, ul2[j].ru)
                    )
                )
                i += 1
                j += 1
            elif t1 < t2:
                i += 1
            else:
                j += 1

        return result

    def _join3(self, ul_q, ul_x, ul_y):
        result = []
        i = j = k = 0
        nx, ny, nq = len(ul_x), len(ul_y), len(ul_q)

        while i < nx and j < ny and k < nq:
            tx, ty, tq = ul_x[i].tid, ul_y[j].tid, ul_q[k].tid

            if tx == ty == tq:
                u = ul_x[i].u + ul_y[j].u - ul_q[k].u
                ru = min(ul_x[i].ru, ul_y[j].ru)
                result.append(ULEntry(tx, u, ru))
                i += 1
                j += 1
                k += 1
            else:
                mn = min(tx, ty, tq)

                if tx == mn:
                    i += 1

                if ty == mn:
                    j += 1

                if tq == mn:
                    k += 1

        return result

    def _dfs(self, prefix, ul_prefix, items, ul_map, min_l, min_u, pt, rl, rp):
        for idx, item in enumerate(items):
            ul_item = ul_map.get(item)

            if not ul_item:
                continue

            u = sum(e.u for e in ul_item)
            ru = sum(e.ru for e in ul_item)

            if u + ru < min_l:
                continue

            pattern = tuple(prefix + [item])

            if u >= min_u:
                pt[pattern] = u
                rl.append((pattern, u))
            elif u >= min_l:
                pt[pattern] = u
                rp.append((pattern, u))

            next_items = items[idx + 1:]

            if not next_items:
                continue

            next_ul_map = {}

            for nxt in next_items:
                ul_nxt = ul_map.get(nxt)

                if not ul_nxt:
                    continue

                if ul_prefix is None:
                    joined = self._join2(ul_item, ul_nxt)
                else:
                    joined = self._join3(ul_prefix, ul_item, ul_nxt)

                if joined:
                    next_ul_map[nxt] = joined

            if next_ul_map:
                self._dfs(
                    prefix + [item],
                    ul_item,
                    next_items,
                    next_ul_map,
                    min_l,
                    min_u,
                    pt,
                    rl,
                    rp
                )

    def _mine(self, global_ul, order, total_utility):
        pt = {}
        rl = []
        rp = []

        min_l = total_utility * self.sl
        min_u = total_utility * self.su

        items = [i for i in order if i in global_ul]
        ul_map = {i: global_ul[i] for i in items}

        self._dfs([], None, items, ul_map, min_l, min_u, pt, rl, rp)

        return pt, rl, rp

    def _check_rescan(self, buf, base):
        if base == 0.0 or self.su >= 1.0:
            return True

        return buf >= ((self.su - self.sl) / (1.0 - self.su)) * base

    def _update_pattern_tree(self, inc_ids):
        if not self.pattern_tree:
            return

        inv = defaultdict(list)

        for pattern in self.pattern_tree:
            for i in pattern:
                inv[i].append(pattern)

        for tid in inc_ids:
            t = self.db[tid]
            t_items = set(t.keys())
            visited = set()

            for i in t_items:
                for pattern in inv.get(i, []):
                    if pattern in visited:
                        continue

                    visited.add(pattern)

                    if all(x in t_items for x in pattern):
                        add_u = sum(self.profits[x] * t[x] for x in pattern)
                        self.pattern_tree[pattern] += add_u

        min_l = self.total_utility * self.sl
        min_u = self.total_utility * self.su

        new_tree = {}
        self.results_large = []
        self.results_pre = []

        for pattern, u in self.pattern_tree.items():
            if u >= min_u:
                new_tree[pattern] = u
                self.results_large.append((pattern, u))
            elif u >= min_l:
                new_tree[pattern] = u
                self.results_pre.append((pattern, u))

        self.pattern_tree = new_tree

    def _rebuild(self, ids):
        trans_iter = self._iter_trans_by_ids(ids)

        global_ul, tu_map = self._construct(trans_iter)

        self.total_utility = sum(tu_map.values())

        min_l = self.total_utility * self.sl

        twu = self._compute_twu(global_ul, tu_map)
        filtered_ul, order = self._filter_and_sort(global_ul, twu, min_l)

        self._reconstruct_ru(filtered_ul, order)

        self.pattern_tree, self.results_large, self.results_pre = self._mine(
            filtered_ul,
            order,
            self.total_utility
        )

    def run(self, db_file, profit_file):
        self.load_data(db_file, profit_file)

        self._orig_base_count = len(self.base_ids)
        self._perf_records = []
        self._prog_start = time.time()

        t0 = time.time()
        m0 = _mem_mb()

        self._rebuild(self.base_ids)

        self.base_utility = self.total_utility

        t1 = time.time()
        m1 = _mem_mb()

        elapsed_base = t1 - t0

        print(f"原始挖掘完成。模式总数：{len(self.pattern_tree)}，large 数量：{len(self.results_large)}")
        print(f"   运行时间：{elapsed_base:.4f} 秒")
        print(f"   内存使用：{m1:.2f} MB")
        print(f"   内存变化：{m1 - m0:+.2f} MB")

        self._perf_records.append(("阶段1（原始挖掘）", elapsed_base, m1, m1 - m0))

        accumulated_inc_ids = []

        for bi, batch_ids in enumerate(self.inc_batches, 1):
            t0 = time.time()
            m0 = _mem_mb()

            batch_tu = 0.0

            for tid in batch_ids:
                t = self.db[tid]
                batch_tu += sum(
                    self.profits.get(i, 0.0) * q
                    for i, q in t.items()
                )

            self.buffer_utility += batch_tu
            self.total_utility += batch_tu
            accumulated_inc_ids.extend(batch_ids)

            label = f"阶段{bi + 1}（增量批次{bi}）"

            if self._check_rescan(self.buffer_utility, self.base_utility):
                print(f"\n============ {label}：触发完全重扫描 ============\n")

                all_ids = self.base_ids + accumulated_inc_ids

                self._rebuild(all_ids)

                self.base_ids = all_ids
                self.base_utility = self.total_utility
                self.buffer_utility = 0.0
                accumulated_inc_ids = []
            else:
                print(f"\n============ {label}：仅更新效用（safety 区域内） ============")

                self._update_pattern_tree(batch_ids)

            self._refresh_memory_order()

            t1 = time.time()
            m1 = _mem_mb()

            elapsed = t1 - t0

            print(f"当前高效用项集数量：{len(self.results_large)}")
            print(f"   运行时间：{elapsed:.4f} 秒")
            print(f"   内存使用：{m1:.2f} MB")
            print(f"   内存变化：{m1 - m0:+.2f} MB")

            self._perf_records.append((label, elapsed, m1, m1 - m0))

        total_elapsed = time.time() - self._prog_start
        final_mem = _mem_mb()
        total_trans = len(self.db)

        print("\n============ 最终挖掘结果汇总 ============")
        print(f"原始数据集大小：{self._orig_base_count} 个事务")
        print(f"处理了 {len(self.inc_batches)} 个增量批次")
        print(f"总事务数：{total_trans}")
        print(f"最终 large 模式数量：{len(self.results_large)}")
        print("最终高效用项集（large，仅项集）：")

        for pattern, _ in sorted(self.results_large, key=lambda x: (len(x[0]), x[0])):
            print("{" + ", ".join(str(i) for i in pattern) + "}")

        print("\n============ 性能统计汇总 ============")

        col_w = 30

        print(f"{'阶段名称':<{col_w}}| {'运行时间(秒)':>16} | {'内存使用(MB)':>16} | {'内存变化(MB)':>16}")

        sep = "-" * 70

        print(sep)

        for name, elapsed, mem, ch in self._perf_records:
            sign = "+" if ch >= 0 else ""
            print(f"{name:<{col_w}}| {elapsed:>16.4f} | {mem:>16.2f} | {sign}{ch:.2f}")

        print(sep)

        init_mem = self._perf_records[0][2] - self._perf_records[0][3]
        prog_ch = final_mem - init_mem
        sign2 = "+" if prog_ch >= 0 else ""

        print(f"{'程序总体运行':<{col_w}}| {total_elapsed:>16.4f} | {final_mem:>16.2f} | {sign2}{prog_ch:.2f}")

        all_elapsed = sum(r[1] for r in self._perf_records)
        peak_mem = max(r[2] for r in self._perf_records)

        print(f"{'总计':<{col_w}}| {all_elapsed:>16.4f} | {peak_mem:>16.2f} | {'峰值内存':>16}")
        print(sep)

        print("\n详细统计：")
        print(f"   峰值内存：{peak_mem:.2f} MB")
        print(f"   平均每阶段时间：{all_elapsed / max(len(self._perf_records), 1):.4f} 秒")
        print(f"   处理了 {len(self._perf_records)} 个阶段")

        return self.results_large


if __name__ == "__main__":
    p = PIHUPM(0.16, 0.1, 0.3)
    L = p.run("mushroom.txt", "mushroomfprofit.txt")
