'''
Ex 1: 
prefix =  [1, 2, 6, 24]              From left to right
postfix = [24, 24, 12, 4]        From right to left
Output:   [24, 12, 8, 6]
'''

class Solution:
    def productExceptSelf(self, nums: List[int]) -> List[int]:
        # Create a result array with the size of len(nums)
        result = [1] * len(nums)

        # Iterate through the prefix
        prefix = 1
        for i in range(len(nums)):
            result[i] *= prefix
            prefix *= nums[i]
        
        # Iterate through the postfix
        postfix = 1
        for i in range(len(nums) - 1, -1, -1):
            result[i] *= postfix
            postfix *= nums[i]
        return result 