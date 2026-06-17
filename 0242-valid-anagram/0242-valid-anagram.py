class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        # Edge case, where length are different
        if len(s) != len(t):
            return False
        charDict = {}
        
        for char in s:
            if char not in charDict:
                charDict[char] = 1
            else:
                charDict[char] += 1
        
        for char in t:
            if char not in charDict or charDict[char] == 0:
                return False
            charDict[char] -= 1
        return True