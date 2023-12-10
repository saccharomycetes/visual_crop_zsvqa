from transformers import CLIPProcessor, CLIPModel
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator, SamPredictor
from ultralytics import YOLO
from PIL import Image
import numpy as np

class crop_tools:
    def __init__(self, device='cpu', clip_model_id="openai/clip-vit-base-patch32", sam_model_path='', yolo_model_path=''):

        self.device = device

        self.clip_model_id = clip_model_id
        self.sam_model_id = sam_model_path
        self.yolo_model_id = yolo_model_path

        self.clip_model, self.clip_processor = self.load_clip()
        self.sam_model = self.load_sam()
        self.yolo_model = self.load_yolo()

    def load_clip(self):
        clip_processor = CLIPProcessor.from_pretrained(self.clip_model_id)
        clip_model = CLIPModel.from_pretrained(self.clip_model_id)
        clip_model.to(self.device)
        return clip_model, clip_processor
    
    def load_sam(self):
        model_types = ['vit_h', 'vit_l', 'vit_b']
        model_type = [model_type for model_type in model_types if model_type in self.sam_model_id][0]
        sam = sam_model_registry[model_type](checkpoint=self.sam_model_id)
        sam.to(self.device)
        sam_model = SamAutomaticMaskGenerator(sam)
        return sam_model
    
    def load_yolo(self):
        yolo_model = YOLO(self.yolo_model_id)
        yolo_model.to(self.device)
        return yolo_model
    
    def clip_score(self, images, text, batch_size):
        all_probs = []
        for i in range(0, len(images), batch_size):
            batch_images = images[i:i+batch_size]
            try:
                inputs = self.clip_processor(
                    images=batch_images,
                    return_tensors="pt",
                    text=[text],
                    padding=True
                ).to(self.device)
                probs = self.clip_model(**inputs).logits_per_image.reshape(-1).detach().cpu().numpy().tolist()
            except:
                probs = [0.0] * len(batch_images)
            all_probs.extend(probs)
        return all_probs
    
    def clip_crop(self, image_path, question, batch_size=4, crop_ratio=0.1, iterations=20):
        image = Image.open(image_path).convert('RGB')
        width, height = image.size
        bbox = (0, 0, width, height)
        for _ in range(iterations):
            crop_width = int((bbox[2] - bbox[0]) * crop_ratio)
            crop_height = int((bbox[3] - bbox[1]) * crop_ratio)
            bbox_candidates = [
                (bbox[0], bbox[1], bbox[2], bbox[3] - crop_height),
                (bbox[0], bbox[1] + crop_height, bbox[2], bbox[3]),
                (bbox[0], bbox[1], bbox[2] - crop_width, bbox[3]),
                (bbox[0] + crop_width, bbox[1], bbox[2], bbox[3]),
            ]
            cropped_images = [image.crop(bbox) for bbox in bbox_candidates]
            scores = self.clip_score(cropped_images, question, batch_size)
            best_index = np.argmax(scores)
            bbox = bbox_candidates[best_index]
        return bbox
    
    def sam_crop(self, image_path, question, batch_size=4):
        image = Image.open(image_path).convert('RGB')
        try:
            masks = self.sam_model.generate(np.array(image))
        except:
            return (0, 0, image.size[0], image.size[1])
        bboxes = [i['bbox'] for i in masks]
        bboxes = [[bbox[0], bbox[1], bbox[0]+bbox[2], bbox[1]+bbox[3]] for bbox in bboxes]
        cropped_images = [image.crop((bbox[0], bbox[1], bbox[2], bbox[3])) for bbox in bboxes]
        if len(cropped_images) == 0:
            return (0, 0, image.size[0], image.size[1])
        scores = self.clip_score(cropped_images, question, batch_size)
        best_index = np.argmax(scores)
        bbox = bboxes[best_index]
        return bbox

    def yolo_crop(self, image_path, question, batch_size=4):
        image = Image.open(image_path).convert('RGB')
        results = self.yolo_model(image_path, save=False)
        bboxes = [[element[0].item(), element[1].item(), element[2].item(), element[3].item()] for element in results[0].boxes.data]
        cropped_images = [image.crop((bbox[0], bbox[1], bbox[2], bbox[3])) for bbox in bboxes]
        if len(cropped_images) == 0:
            return (0, 0, image.size[0], image.size[1])
        scores = self.clip_score(cropped_images, question, batch_size)
        best_index = np.argmax(scores)
        bbox = bboxes[best_index]
        return bbox