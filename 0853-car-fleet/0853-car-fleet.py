'''
target = 12
position = [10,8,0,5,3]
speed = [2,4,1,1,3]
time = [(10, 1), (8, 1), (5, 7), (3, 3), (0, 12)]
'''

class Solution:
    def carFleet(self, target: int, position: List[int], speed: List[int]) -> int:
        n = len(position)
        cars = []
        # populate cars array ()
        for i in range(n):
            time = (target - position[i]) / speed[i]
            cars.append((position[i], time))
        
        # sort by position, closest to target first
        cars.sort(reverse=True)
        
        result, lead = 0, 0

        for pos, t in cars:
            if t > lead:
                result += 1
                lead = t
        return result


                    

        