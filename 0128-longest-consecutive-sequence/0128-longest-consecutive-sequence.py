class Solution:
    def longestConsecutive(self, nums: List[int]) -> int:
        numSet = set()
        res = 0
        # Add all numbers to a set
        for num in nums:
            numSet.add(num)

        for num in numSet:
            # Only start counting when num is the beginning of a sequence
            if num - 1 not in numSet:
                length = 1

                while num + length in numSet:
                    length += 1

                res = max(res, length)
        return res