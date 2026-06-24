class Solution:
    def characterReplacement(self, s: str, k: int) -> int:
        charFreq = defaultdict(int)
        left, right, res = 0, 0, 0
        
        while right < len(s):
            if s[right] not in charFreq:
                charFreq[s[right]] = 1
            else:
                charFreq[s[right]] += 1
            temp = (right - left + 1 ) - max(charFreq.values())
            # temp > k means this substring is invalid
            # temp < k means this substring is valid => get current substring length
            while temp > k:
                charFreq[s[left]] -= 1
                left += 1
                # Recalculate temp
                temp = (right - left + 1 ) - max(charFreq.values())
            res = max(res, right - left + 1)
            # Update outer while loop condition
            right += 1

        return res
