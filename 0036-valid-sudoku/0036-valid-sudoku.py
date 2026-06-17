class Solution:
    def isValidSudoku(self, board: List[List[str]]) -> bool:
        # Sudoku is fixed size, so it's easier

        # Iterate through the sudoku board once, add the value to 3 dictionary, and check duplicates
        rows, cols, squares = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
        for i in range(9):
            for j in range(9):
                if board[i][j] == ".":
                    continue
                if board[i][j] in rows[i] or board[i][j] in cols[j] or board[i][j] in squares[(i // 3, j // 3)]:
                    return False 
                rows[i].add(board[i][j])
                cols[j].add(board[i][j])
                squares[(i // 3, j // 3)].add(board[i][j])
        return True