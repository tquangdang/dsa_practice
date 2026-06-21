class Solution:
    def lengthOfLongestSubstring(self, s: str) -> int:
        # Edge case:
        if len(s) <= 1:
            return len(s)

        left, right = 0, 0
        res = 0
        charSet = set()
        
        while right < len(s):
            if s[right] not in charSet:
                charSet.add(s[right]) 
                res = max(res, right - left + 1)
                right += 1
            else:
                while s[right] in charSet:
                    charSet.remove(s[left])
                    left += 1
        
        return res
