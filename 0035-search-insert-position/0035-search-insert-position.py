class Solution:
    def searchInsert(self, nums: List[int], target: int) -> int:
        start, end = 0, len(nums) - 1
        
        '''
        last loop iteration happens when mid == start == end, meaning 3 cases
        1) found target at mid --> return mid as insert index
        2) target > nums[mid] --> nums[mid] is the largest number smaller than target
        --> insert at mid + 1 (which is also end + 1)
        3) target < nums[mid] --> start = mid + 1 --> nums[mid] is the smallest number larger than target -->
        '''
        while start <= end:
            mid = start + (end - start) // 2
            if nums[mid] == target:
                return mid
            elif nums[mid] < target:
                start = mid + 1
            else:
                end = mid - 1
                
        return end + 1