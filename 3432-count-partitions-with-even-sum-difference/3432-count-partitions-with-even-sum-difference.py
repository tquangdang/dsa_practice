class Solution:
    def countPartitions(self, nums: List[int]) -> int:
        res, leftSum = 0, 0
        rightSum = sum(nums)

        for i in range(len(nums) - 1):
            leftSum += nums[i]
            rightSum -= nums[i]
            if (leftSum - rightSum) % 2 == 0:
                res += 1
        return res