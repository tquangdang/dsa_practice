class Solution:
    def minEatingSpeed(self, piles: List[int], h: int) -> int:
        low, high = 1, max(piles)
        total_bananas = sum(piles)
        while low <= high:
            mid =(low + high) // 2
            hours = sum(math.ceil(pile / mid) for pile in piles)

            if hours > h:          # too slow (N)
                low = mid + 1
            else:                  # finishes in time (Y) — keep as candidate
                high = mid - 1

        return low
