class Solution:
    def plusOne(self, digits: List[int]) -> List[int]:
        # Turn the digits array into the actual integer
        integer = ""
        res = []
        for digit in digits:
            integer += str(digit)
        # Perform the calculation
        integer = str(int(integer) + 1)
        # Convert the string character to integer, and add to result
        for digit in integer:
            res.append(int(digit))
        return res