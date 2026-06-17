class Solution:
    def isPalindrome(self, s: str) -> bool:
        # lowercase the string, and remove whitespace
        temp_s = ""

        for char in s:
            if  char.isalnum():
                temp_s += char.lower()
        
        # 2 pointers to check palindrome
        left, right = 0, len(temp_s) - 1
        while left < right:
            if temp_s[left] != temp_s[right]:
                return False
            left += 1
            right -= 1
            
        return True