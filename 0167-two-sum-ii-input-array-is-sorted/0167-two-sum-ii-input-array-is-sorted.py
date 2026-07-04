class Solution:
    def twoSum(self, numbers: List[int], target: int) -> List[int]:
        # Initialize 2 pointers at the beginning and end of the array
        start, end = 0, len(numbers) - 1
        
        # Loop through the array
        while start < end:
            total = numbers[start] + numbers[end]
            if total < target:
                start += 1
            elif total > target:
                end -= 1
            else:
                return [start + 1, end + 1]