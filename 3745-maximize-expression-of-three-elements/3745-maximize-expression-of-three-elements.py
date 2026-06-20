class Solution:
    def maximizeExpressionOfThree(self, nums: List[int]) -> int:
        # Inverse all elements to make a min heap a max heap
        for i in range(len(nums)):
            nums[i] *= -1 
        heapify(nums)  

        # Pop the largest and second largest value, and subtract by the minimum value
        return -1 * heappop(nums) +  -1 * heappop(nums) -  -1 * max(nums)