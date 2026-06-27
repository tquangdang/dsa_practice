'''
A valid window should be:
- Start with a char in s
- End with a char in s'
- Minimum length

'''
class Solution:
    def minWindow(self, s: str, t: str) -> str:
        t_freq = Counter(t)
        have, need = 0, len(set(t)) 
        s_freq = Counter()
        result = ""
        left, right = 0, 0
        while right < len(s):
            if s[right] in t_freq:
                s_freq[s[right]] += 1
                # When should have increase?
                # Hint: Only when s_freq[char] FIRST reaches t_freq[char]
                if s_freq[s[right]] == t_freq[s[right]]:
                    have += 1
            while have == need:
                if right - left + 1 < len(result) or result == "":
                    result = s[left:right + 1]
                # Shrinking the window
                if s[left] in t_freq:
                    if s_freq[s[left]] == t_freq[s[left]]:
                        have -= 1
                    s_freq[s[left]] -= 1
                left += 1
                while left < right and s[left] not in t_freq:
                    left += 1
            right += 1
        return result