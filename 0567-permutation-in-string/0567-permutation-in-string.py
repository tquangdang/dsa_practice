class Solution:
    def checkInclusion(self, s1: str, s2: str) -> bool:
        # Counter is a special dictionary in Python that counts how many times each item appears.
        need = Counter(s1)
        cur_window = Counter()

        # Create 2 pointers for sliding window
        left, right = 0, 0
        while right < len(s2):
            cur_window[s2[right]] += 1

            # Maintain the length of the window
            if right - left + 1 > len(s1):
                cur_window[s2[left]] -= 1
                # If frequency reached zero, delete it from dictionary
                if cur_window[s2[left]] == 0:
                    del cur_window[s2[left]]
                left += 1

            # Window is now at most len(s1)
            if need == cur_window:
                return True
            right += 1
        return False
                