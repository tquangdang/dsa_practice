class Solution:
    def containsDuplicate(self, nums: List[int]) -> bool:
        # Create a set that store unique number
        numSet = set()

        for num in nums:
            if num not in numSet:
                numSet.add(num)
            else:
                return True
        return False