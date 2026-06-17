class Solution:
    def largestAltitude(self, gain: List[int]) -> int:
        prefix = [0]
        
        for i in range(len(gain)):
            prefix.append(prefix[i] + gain[i])
            
        return max(prefix)