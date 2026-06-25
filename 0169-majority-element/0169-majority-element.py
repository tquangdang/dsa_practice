'''
brute force: create a dictionary, log the frequency of each number, and return the number with max frequency. O(N) time O(N) space


1 3 5 7 9 9 9,9,9
1 has 1 vote, 8 remaining votes
3 has 1 vote, 1's 1 vote gets cancelled out, 7 remaining votes


vote of the most frequent candidate is always positive

9 9 1 9 3 9 5 9 7  

res = num = 1
frequency = 0

num = 3


optimized: the majority number always has the highest frequency in the list, compare to other numbers. traverse the list, keep count of current number. whenever encouter a number that is not the previously saved number, cancel out that number by decreasing its frequency. 
'''

class Solution:
    def majorityElement(self, nums: List[int]) -> int:
        res, frequency = 0, 0
        
        for num in nums:
            # if 
            if frequency == 0:
                res = num
            # if current number is still the last saved number, increment frequency
            if num == res:
                frequency += 1
            # if current number is not the last saved number, decrement frequency
            else:
                frequency -= 1
        return res