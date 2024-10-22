# import list
from typing import List
class Solution:
    def generate (self, numRows: int) -> List[List[int]]:
        first_row = [1]
        rows = [first_row]

        for _ in range(1, numRows):
            # start with 1
            row = [1]
            for i in range(1, len(rows[-1])):
                num = rows[-1][i-1] + rows[-1][i]
                row.append(num)
            row.append(1)
            rows.append(row)
        return rows
    
# Test with input 9
tes1 = Solution()
print(tes1.generate(9))