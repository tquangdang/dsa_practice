'''
- optimal solution: fast and slow pointer
- how it works
    - define a sum_square function that takes in a number n, and return the sum of the square of its digits
    - initialize two "pointers," slow is n and fast is sum_square(n). fast is always one iteration ahead of slow
    - while slow != fast, "move" both pointers ahead by one iteration of sum_square()
    - if slow == fast, the loop exits, we find a cycle, which means n is not a happy number, which will never ends in 1
    - otherwise, if slow = 1 or fast = 1, n is a happy number
- time: O(logn), where n is the input number. Each step needs us to process all its digits, which takes about O(log n) time since a number with n value has roughly (log n) digits. The sequence quickly falls into a small range of numbers, so the number of steps is constant. That’s why the overall time complexity is O(log n).
- why it works:
    - a happy number sequence will reach 1. a non-happy number will get stuck in a cycle --> use fast and slow pointers to detect a cycle
    - this method avoids storing numbers in a hash set, making it a o(1) space solution
'''

class Solution:
    def isHappy(self, n: int) -> bool:
        # Function that execute the process once
        def sum_square(num):
            sum = 0
            
            while num > 0:
                digit = num % 10
                sum += digit * digit
                num //= 10              
                # a // b: The quotient of a divided by b, rounded to the next smallest whole number eg. 49 // 10 = 4
            return sum
        
        slow = n
        fast = sum_square(n)
        
        while slow != fast:
            slow = sum_square(slow)
            fast = sum_square(sum_square(fast))
        
        if slow == 1 or fast == 1:
            return True
            
        return False
       