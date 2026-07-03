class Solution:
    def searchMatrix(self, matrix: List[List[int]], target: int) -> bool:
        # Search for the target row
        top, bottom = 0, len(matrix) - 1
        row = 0
        while top <= bottom:
            mid = (top + bottom) // 2
            if matrix[mid][0] < target:
                if matrix[mid][-1] < target:
                    top = mid + 1
                elif matrix[mid][-1] == target: 
                    return True
                else:
                    row = mid
                    break
            elif matrix[mid][0] > target:
                bottom -= 1
            else:
                return True

        # Search in that row
        left, right = 0, len(matrix[0]) - 1
        while left <= right:
            mid = (left + right) // 2
            if matrix[row][mid] < target:
                left = mid + 1
            elif matrix[row][mid] > target:
                right = mid - 1
            else:
                return True
        return False

        