class Solution:
    def minWindow(self, s: str, t: str) -> str:
        t_freq = Counter(t)

        have = 0
        need = len(t_freq)

        s_freq = Counter()

        result = ""

        left = 0
        right = 0

        while right < len(s):

            if s[right] in t_freq:
                s_freq[s[right]] += 1

                if s_freq[s[right]] == t_freq[s[right]]:
                    have += 1

            # Current window has everything needed.
            while have == need:

                # Only update result if this window is better.
                if result == "" or right - left + 1 < len(result):
                    result = s[left:right + 1]

                # But ALWAYS shrink the window.
                if s[left] in t_freq:

                    # Removing this character will make the window invalid.
                    if s_freq[s[left]] == t_freq[s[left]]:
                        have -= 1

                    s_freq[s[left]] -= 1

                left += 1

            right += 1

        return result