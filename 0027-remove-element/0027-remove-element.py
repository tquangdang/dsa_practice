class Solution:
    def removeElement(self, nums: List[int], val: int) -> int:
        # Two pointers approach
        start, end = 0, len(nums) - 1
        # Initialize k to count numbers equal to k
        k = 0
        
        while start <= end:
            if nums[start] == val:
                if nums[end] == val:
                    end -= 1
                else:
                    nums[start], nums[end] = nums[end], nums[start]
                    start += 1
                    end -= 1
                k += 1  
            else:
                start += 1
        return len(nums) - k
        