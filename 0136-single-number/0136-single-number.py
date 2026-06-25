class Solution:
    def singleNumber(self, nums: List[int]) -> int:
        # We use the XOR operation for this problem. 
        # If a number shows up twice, the first time 
        # it “adds in,” the second time it “cancels out.”
        result = 0
        for num in nums:
            result ^= num
        return result