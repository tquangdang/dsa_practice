class Solution(object):
    def trap(self, height):
        """
        :type height: List[int]
        :rtype: int
        """
        # two pointers at beginning and end of array
        left = 0
        right = len(height) - 1
		
        higher_level = 0 # keep track of "highest" level of water seen so far
        water = 0 # total water
		
        while left < right:
            if height[left] <= height[right]:
		# if left pointer has lower level, store the value and move it one step to right
                lower_level = height[left]
                left += 1
            else:
		# if right pointer has lower level, store the value and move it one step to left
                lower_level = height[right]
                right -= 1
				
	    # make sure to store and continuously update the current "highest" level of water
            higher_level = max(higher_level, lower_level)
			
            # incrementally keep track of amount of water so far
            water += higher_level - lower_level
			
        return water