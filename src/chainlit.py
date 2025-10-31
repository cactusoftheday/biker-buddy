import chainlit as cl
import os
from pathlib import Path

# Global counter to track message count
message_count = 0

@cl.on_message
async def echo_message(message: cl.Message):
    global message_count
    
    # Get list of images from /images directory
    images_dir = Path("/home/isaac/biker/images")
    
    # Get all image files (common formats)
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    image_files = []
    
    if images_dir.exists():
        for ext in image_extensions:
            image_files.extend(images_dir.glob(f"*{ext}"))
            image_files.extend(images_dir.glob(f"*{ext.upper()}"))
    
    # Sort files for consistent ordering
    image_files = sorted(image_files)
    
    if image_files:
        # Get the image for this message (cycle through available images)
        image_index = message_count % len(image_files)
        selected_image = image_files[image_index]
        
        # Create image element
        image_element = cl.Image(
            name=f"image_{message_count + 1}",
            display="inline",
            path=str(selected_image)
        )
        
        # Send response with image
        await cl.Message(
            content=f"You said: {message.content}\n\nHere's image {message_count + 1}:",
            elements=[image_element]
        ).send()
        
        message_count += 1
    else:
        # No images found
        await cl.Message(
            content=f"You said: {message.content}\n\nNo images found in /images directory."
        ).send()