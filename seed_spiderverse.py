"""
seed_spiderverse.py
--------------------
One-off script to load the "Spider-Verse Hackathon" problem sets into Mongo,
wired up for the new HackerRank-style Code & Run editor.

WHY ONLY THE 3 SORTING PROBLEMS GET AUTO-GRADED TEST CASES:
The 3 billing/simulation problems (Spider-Gear Shop, Pizza-Time, Ticket
Booking) are interactive - they print input prompts via input("...") and
those prompts would end up mixed into stdout. The original question doc
itself says these are "free-form (no auto-judge test cases provided) since
they depend on print formatting". So they're seeded as problem_type="file"
(same manual-review flow the app already had). The 3 sorting problems are
pure stdin -> stdout transforms, so they're seeded as problem_type="code"
with a real judge: 9 test cases each (1 sample + 8 hidden), matching the
constraints in the question doc (large N, duplicates, negatives, etc.)

Run with the same MONGO_URI your app uses, e.g.:
    MONGO_URI="mongodb+srv://...&appName=Cluster0" python3 seed_spiderverse.py
"""

import os
import random
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise SystemExit("Set MONGO_URI before running this seed script.")

EVENT_TITLE = "Spider-Verse Hackathon"


def make_test(input_text, output_text, is_sample, order):
    return {"input": input_text, "output": output_text, "is_sample": is_sample, "order": order}


# ---------------------------------------------------------------- #
# SORT 1 - Kth strongest henchman (kth largest element, 1-indexed)
# ---------------------------------------------------------------- #

def kth_largest_case(n, k, values):
    inp = f"{n} {k}\n{' '.join(map(str, values))}\n"
    out = str(sorted(values, reverse=True)[k - 1])
    return inp, out


def build_sort1_tests():
    tests = []
    rng = random.Random(1)

    # Sample from the question doc
    inp, out = kth_largest_case(6, 3, [7, 10, 4, 3, 20, 15])
    tests.append(make_test(inp, out, True, 1))

    # single element
    inp, out = kth_largest_case(1, 1, [42])
    tests.append(make_test(inp, out, False, 2))

    # all equal
    vals = [7] * 500
    inp, out = kth_largest_case(500, 250, vals)
    tests.append(make_test(inp, out, False, 3))

    # k = 1 (max) and k = n (min)
    vals = rng.sample(range(0, 10**6), 1000)
    inp, out = kth_largest_case(1000, 1, vals)
    tests.append(make_test(inp, out, False, 4))
    inp, out = kth_largest_case(1000, 1000, vals)
    tests.append(make_test(inp, out, False, 5))

    # large values near 1e9
    vals = [rng.randint(999_000_000, 10**9) for _ in range(2000)]
    inp, out = kth_largest_case(2000, 777, vals)
    tests.append(make_test(inp, out, False, 6))

    # zeros included
    vals = [0] * 100 + list(range(1, 401))
    rng.shuffle(vals)
    inp, out = kth_largest_case(500, 450, vals)
    tests.append(make_test(inp, out, False, 7))

    # N = 100000 random
    vals = [rng.randint(0, 10**9) for _ in range(100_000)]
    inp, out = kth_largest_case(100_000, 50_000, vals)
    tests.append(make_test(inp, out, False, 8))

    # N = 100000, k = N (smallest element)
    inp, out = kth_largest_case(100_000, 100_000, vals)
    tests.append(make_test(inp, out, False, 9))

    return tests


# ---------------------------------------------------------------- #
# SORT 2 - Count inversions
# ---------------------------------------------------------------- #

def count_inversions(arr):
    # O(n log n) merge-sort based counter (used only to compute expected output)
    def sort_count(a):
        if len(a) <= 1:
            return a, 0
        mid = len(a) // 2
        left, cl = sort_count(a[:mid])
        right, cr = sort_count(a[mid:])
        merged, cm = [], 0
        i = j = 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i]); i += 1
            else:
                merged.append(right[j]); j += 1
                cm += len(left) - i
        merged.extend(left[i:]); merged.extend(right[j:])
        return merged, cl + cr + cm

    _, count = sort_count(arr)
    return count


def inversions_case(values):
    inp = f"{len(values)}\n{' '.join(map(str, values))}\n"
    out = str(count_inversions(values))
    return inp, out


def build_sort2_tests():
    tests = []
    rng = random.Random(2)

    inp, out = inversions_case([2, 4, 1, 3, 5])
    tests.append(make_test(inp, out, True, 1))

    inp, out = inversions_case([5])
    tests.append(make_test(inp, out, False, 2))

    inp, out = inversions_case([1, 2, 3, 4, 5, 6, 7, 8])  # already sorted -> 0
    tests.append(make_test(inp, out, False, 3))

    inp, out = inversions_case([9, 8, 7, 6, 5, 4, 3, 2, 1])  # fully reversed small
    tests.append(make_test(inp, out, False, 4))

    vals = [rng.randint(-1000, 1000) for _ in range(2000)]
    inp, out = inversions_case(vals)
    tests.append(make_test(inp, out, False, 5))

    vals = [5] * 3000  # all equal -> 0 inversions
    inp, out = inversions_case(vals)
    tests.append(make_test(inp, out, False, 6))

    vals = [rng.randint(-10**9, 10**9) for _ in range(20_000)]
    inp, out = inversions_case(vals)
    tests.append(make_test(inp, out, False, 7))

    # N = 100000 fully reverse-sorted -> max inversions = 4999950000
    vals = list(range(100_000, 0, -1))
    inp, out = inversions_case(vals)
    tests.append(make_test(inp, out, False, 8))

    vals = [rng.randint(-10**9, 10**9) for _ in range(100_000)]
    inp, out = inversions_case(vals)
    tests.append(make_test(inp, out, False, 9))

    return tests


# ---------------------------------------------------------------- #
# SORT 3 - Sort ascending
# ---------------------------------------------------------------- #

def sort_case(values):
    inp = f"{len(values)}\n{' '.join(map(str, values))}\n"
    out = " ".join(map(str, sorted(values)))
    return inp, out


def build_sort3_tests():
    tests = []
    rng = random.Random(3)

    inp, out = sort_case([9, 2, 7, 4, 1])
    tests.append(make_test(inp, out, True, 1))

    inp, out = sort_case([42])
    tests.append(make_test(inp, out, False, 2))

    inp, out = sort_case([3] * 1000)  # duplicates only
    tests.append(make_test(inp, out, False, 3))

    vals = [rng.randint(-10**9, 10**9) for _ in range(1000)]
    inp, out = sort_case(vals)
    tests.append(make_test(inp, out, False, 4))

    vals = list(range(5000, -5000, -1))  # reverse sorted negatives + positives
    inp, out = sort_case(vals)
    tests.append(make_test(inp, out, False, 5))

    vals = [0] * 5000
    inp, out = sort_case(vals)
    tests.append(make_test(inp, out, False, 6))

    vals = [rng.randint(-10**9, 10**9) for _ in range(50_000)]
    inp, out = sort_case(vals)
    tests.append(make_test(inp, out, False, 7))

    vals = [rng.randint(-10**9, 10**9) for _ in range(100_000)]
    inp, out = sort_case(vals)
    tests.append(make_test(inp, out, False, 8))

    vals = list(range(100_000, 0, -1))
    inp, out = sort_case(vals)
    tests.append(make_test(inp, out, False, 9))

    return tests


# ---------------------------------------------------------------- #
# Starter code templates
# ---------------------------------------------------------------- #

STARTER_PY_KTH = """# Read N and K, then N space-separated power levels.
# Print the K-th LARGEST power level.

n, k = map(int, input().split())
powers = list(map(int, input().split()))

# TODO: implement without using sorted()/list.sort() directly if you want
# full marks for a selection-based approach (heap / quickselect).
"""

STARTER_PY_INV = """# Read N, then N space-separated timestamps (can be negative).
# Print the number of inversions (i < j with a[i] > a[j]).
# Naive O(N^2) will TLE on the largest cases - use merge-sort counting.

n = int(input())
arr = list(map(int, input().split()))
"""

STARTER_PY_SORT = """# Read N, then N space-separated integers (can be negative).
# Print them in ascending order, space-separated.
# Implement your own sort (merge sort / quick sort) instead of sorted().

n = int(input())
arr = list(map(int, input().split()))
"""

STARTER_CPP = """#include <bits/stdc++.h>
using namespace std;

int main() {
    // your code here
    return 0;
}
"""

STARTER_C = """#include <stdio.h>

int main() {
    // your code here
    return 0;
}
"""

STARTER_JAVA = """import java.util.*;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        // your code here
    }
}
"""


def main():
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()

    event = db.events.find_one({"title": EVENT_TITLE})
    if not event:
        from datetime import datetime
        result = db.events.insert_one({
            "title": EVENT_TITLE,
            "description": "Sorting + simulation challenges across the Spider-Verse.",
            "start_date": datetime(2026, 1, 1),
            "end_date": datetime(2026, 12, 31),
        })
        event_id = str(result.inserted_id)
        print(f"Created event '{EVENT_TITLE}' -> {event_id}")
    else:
        event_id = str(event["_id"])
        print(f"Using existing event '{EVENT_TITLE}' -> {event_id}")

    def upsert_problem(title, problem_type, **fields):
        existing = db.problem_statements.find_one({"event_id": event_id, "title": title})
        doc = {"event_id": event_id, "title": title, "problem_type": problem_type, **fields}
        if existing:
            db.problem_statements.update_one({"_id": existing["_id"]}, {"$set": doc})
            pid = str(existing["_id"])
            db.test_cases.delete_many({"problem_id": pid})
            print(f"Updated problem '{title}' -> {pid}")
        else:
            result = db.problem_statements.insert_one(doc)
            pid = str(result.inserted_id)
            print(f"Inserted problem '{title}' -> {pid}")
        return pid

    # ---- SET 1 ----
    pid = upsert_problem(
        "The K-th Strongest Henchman", "code",
        difficulty="Easy",
        description=(
            "Peter has hacked into Kingpin's servers and pulled a list of N henchmen with "
            "their power levels. He needs to know who the K-th strongest henchman is, so he "
            "knows exactly how much muscle he's up against."
        ),
        input_format="Line 1: N K\nLine 2: N space-separated power levels",
        output_format="A single integer — the K-th largest power level",
        constraints=(
            "1 <= K <= N <= 100000\n0 <= power level <= 10^9\n"
            "No built-in \"find kth\" library shortcuts — solve via a sorting-based or "
            "selection approach (quickselect / heap / sort)."
        ),
        sample_input="6 3\n7 10 4 3 20 15\n",
        sample_output="10",
        time_limit_ms=2000,
        starter_code={"python3": STARTER_PY_KTH, "cpp": STARTER_CPP, "c": STARTER_C, "java": STARTER_JAVA},
        max_size_mb=20,
    )
    for t in build_sort1_tests():
        t["problem_id"] = pid
        db.test_cases.insert_one(t)

    upsert_problem(
        "Spider-Gear Shop Billing System", "file",
        difficulty="Easy",
        description=(
            "Peter needs gear before patrol. Build a program that takes hero registration "
            "details, shows a gear menu, lets the user pick an item and quantity, applies a "
            "tiered discount based on total bill value, and prints a formatted final bill. "
            "See the full spec (menu, discount tiers, sample I/O) in the event brief. "
            "Discount tiers: Bill >= 50000 -> 15% off, Bill >= 20000 -> 10% off, else no "
            "discount."
        ),
        max_size_mb=20,
    )

    # ---- SET 2 ----
    pid = upsert_problem(
        "Count the Out-of-Order Pairs", "code",
        difficulty="Hard",
        description=(
            "J. Jonah Jameson has a strip of N photo-timestamps that got shuffled by MJ. He "
            "wants to know how many pairs of photos are in the wrong relative order (a "
            "later-index photo has a smaller timestamp than an earlier one) before deciding "
            "whether it's worth re-sorting them for print. This is the classic inversion "
            "count problem."
        ),
        input_format="Line 1: N\nLine 2: N space-separated integers (timestamps, can be negative)",
        output_format="A single integer — the number of inversions (pairs i<j with a[i] > a[j])",
        constraints=(
            "1 <= N <= 100000\n-10^9 <= value <= 10^9\n"
            "Output can be as large as ~5x10^9 — use a 64-bit integer type.\n"
            "Naive O(N^2) will TLE on the large cases; use merge-sort based counting "
            "(O(N log N)) for full marks."
        ),
        sample_input="5\n2 4 1 3 5\n",
        sample_output="3",
        time_limit_ms=3000,
        starter_code={"python3": STARTER_PY_INV, "cpp": STARTER_CPP, "c": STARTER_C, "java": STARTER_JAVA},
        max_size_mb=20,
    )
    for t in build_sort2_tests():
        t["problem_id"] = pid
        db.test_cases.insert_one(t)

    upsert_problem(
        "Pete's Pizza-Time Billing System", "file",
        difficulty="Medium",
        description=(
            "Between web-slinging, Peter delivers pizza. Build a program that takes customer "
            "details, displays a food menu, lets the customer order multiple items in a loop, "
            "adds a 5% delivery tax, applies a flat Rs.100 'Friendly Neighborhood Discount' for "
            "groups of 4+, adds a Rs.30 late fee if applicable, and prints an itemized bill. "
            "Full menu and sample interaction are in the event brief."
        ),
        max_size_mb=20,
    )

    # ---- SET 3 ----
    pid = upsert_problem(
        "Sort the Multiverse Signals", "code",
        difficulty="Medium",
        description=(
            "Miguel O'Hara's dimensional tracker picked up N signal strengths from across the "
            "Spider-Verse. Sort them in ascending order so the team can scan from weakest to "
            "strongest anomaly."
        ),
        input_format="Line 1: N\nLine 2: N space-separated integers (can be negative)",
        output_format="N space-separated integers in ascending order",
        constraints=(
            "1 <= N <= 100000\n-10^9 <= value <= 10^9\n"
            "No built-in sort function allowed — implement manually (merge sort / quick sort "
            "recommended; bubble/insertion sort will be too slow at N=100000)."
        ),
        sample_input="5\n9 2 7 4 1\n",
        sample_output="1 2 4 7 9",
        time_limit_ms=2000,
        starter_code={"python3": STARTER_PY_SORT, "cpp": STARTER_CPP, "c": STARTER_C, "java": STARTER_JAVA},
        max_size_mb=20,
    )
    for t in build_sort3_tests():
        t["problem_id"] = pid
        db.test_cases.insert_one(t)

    upsert_problem(
        "Spider-Verse Exhibit Ticket Booking", "file",
        difficulty="Medium",
        description=(
            "Build a program for visitor registration and exhibit ticket booking: show slots "
            "and prices, let the visitor pick a slot and ticket count, apply age-based and "
            "group-size discounts, add a flat Rs.20 cleanup fee per ticket, and print the "
            "final bill. Full slot list and sample interaction are in the event brief."
        ),
        max_size_mb=20,
    )

    print("\nDone. 3 code problems (with 9 test cases each) + 3 file-upload problems seeded.")


if __name__ == "__main__":
    main()
